"""Self-checks for the AI-triage plumbing and the digest renderer.
No network: llm.complete / llm._post are monkeypatched."""
import asyncio
import datetime
import json
import re
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import ai_generator
import llm
from ai_generator import TRIAGE_VERSION, TriageParseError, parse_triage
from conftest import fake_providers, resp
from database import Base, Job
from digest import build_digest, render_digest
from scan_service import _apply_triage, triage_jobs


def _job(**kw):
    base = dict(id=1, title="Software Engineer", company="Acme", location="Barcelona, ES",
                url="https://x/y", match_score=40.0, ai_score=None, ai_verdict="",
                sponsorship="", dealbreakers="[]", description="")
    base.update(kw)
    return Job(**base)


def _a(jid, score=50, verdict="ok"):
    return {"id": jid, "fit_score": score, "verdict": verdict, "sponsorship": "no", "dealbreakers": []}


def _memory_db():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)


def test_apply_triage():
    j = _job()
    _apply_triage(j, {"fit_score": 71.0, "verdict": "Great new-grad fit",
                      "sponsorship": "likely", "dealbreakers": ["Requires German"]}, "groq", "gpt-oss")
    assert j.ai_score == 71.0 and j.fit_score == 71.0
    assert j.sponsorship == "likely"
    assert json.loads(j.dealbreakers) == ["Requires German"]
    assert j.ai_assessed_at is not None
    assert (j.ai_provider, j.ai_model, j.triage_version) == ("groq", "gpt-oss", TRIAGE_VERSION)


def test_fit_score_never_falls_back_to_keywords():
    assert _job(ai_score=None, match_score=72.0).fit_score is None
    assert _job(ai_score=68.0, match_score=72.0).fit_score == 68.0


def test_render_digest_ranking_and_subject():
    jobs = [
        _job(id=1, ai_score=30.0),
        _job(id=2, ai_score=90.0, ai_verdict="Strong", sponsorship="yes"),
        _job(id=3, ai_score=None, match_score=95.0),   # pending: never counts as strong
        _job(id=4, ai_score=70.0),
    ]
    subject, html = render_digest(jobs)
    assert "4 new job" in subject
    assert "2 strong match" in subject                 # 90 and 70, not the pending one
    assert html.index("90%") < html.index("70%")
    assert "30%" not in html and "95%" not in html
    assert "+ 2 more" in html
    assert "Strong" in html and "sponsors" in html.lower()


def test_render_digest_shows_pending_not_a_percentage():
    subject, html = render_digest([_job(id=1, ai_score=None, match_score=80.0)])
    assert "pending" in html and "80%" not in html


def test_render_digest_empty():
    assert render_digest([]) is None


def test_one_score_across_list_stats_and_digest():
    """The bug: stats read match_score, the job card read coalesce(ai, match).
    Same job must show the same number everywhere, and a pending job none."""
    from routes.jobs import list_jobs
    from routes.stats import get_stats

    db = _memory_db()()
    now = datetime.datetime.utcnow()
    db.add_all([
        Job(url="https://x/assessed", title="Assessed", company="C", last_seen=now,
            match_score=72.0, ai_score=68.0, ai_verdict="ok"),
        Job(url="https://x/pending", title="Pending", company="C", last_seen=now,
            match_score=90.0, ai_score=None),
    ])
    db.commit()
    a_id = db.query(Job).filter(Job.title == "Assessed").one().id

    listed = {j["title"]: j for j in list_jobs(db=db, source=None, status=None, min_score=0,
                                              location=None, sponsorship=None)}
    stats = get_stats(db=db)
    _, html = build_digest(db, [j.id for j in db.query(Job)])

    assert listed["Assessed"]["fit_score"] == 68.0 and listed["Assessed"]["assessed"]
    assert listed["Pending"]["fit_score"] is None and not listed["Pending"]["assessed"]
    assert "match_score" not in listed["Assessed"]
    assert [j["title"] for j in listed.values()] == ["Assessed", "Pending"]  # scored first
    assert stats["top_jobs"] == [{"id": a_id, "title": "Assessed", "company": "C", "score": 68.0}]
    assert stats["avg_score"] == 68.0 and stats["assessed"] == 1 and stats["total_jobs"] == 2
    assert stats["score_distribution"] == {"90-100": 0, "70-89": 0, "50-69": 1, "0-49": 0}
    score_cells = re.findall(r'color:#6366f1;white-space:nowrap">([^<]+)</td>', html)
    assert score_cells == ["68%"]  # pending one held back behind the strong match
    # min_score filters on the fit score; a pending job has none to pass
    assert [j["title"] for j in list_jobs(db=db, source=None, status=None, min_score=60,
                                          location=None, sponsorship=None)] == ["Assessed"]


# ── parse_triage: alignment by id, never by position ─────────────────────────

def test_parse_aligns_by_id_not_position():
    raw = json.dumps([_a(7, 20, "seven"), _a(3, 90, "three")])
    out = parse_triage(raw, [3, 7])
    assert [o["verdict"] for o in out] == ["three", "seven"]


@pytest.mark.parametrize("raw", [
    "not json",
    json.dumps([_a(1)]),                                      # too short
    json.dumps([_a(1), _a(2), _a(3)]),                        # too long
    json.dumps([_a(1), _a(1)]),                               # duplicate id
    json.dumps([_a(1), _a(9)]),                               # unknown id
    json.dumps([_a(1), {"fit_score": 50, "verdict": "x"}]),   # missing id
    json.dumps([_a(1), _a(2, score="high")]),                 # bad score
    json.dumps([_a(1), _a(2, score=140)]),                    # out of range
    json.dumps([_a(1), _a(2, verdict="")]),                   # empty verdict
    json.dumps(_a(1)),                                        # one object for two jobs
])
def test_parse_rejects(raw):
    with pytest.raises(TriageParseError):
        parse_triage(raw, [1, 2])


def test_parse_fenced_single_object():
    out = parse_triage('```json\n{"id": 5, "fit_score": 55, "verdict": "ok", '
                       '"sponsorship": "NO", "dealbreakers": ["x", ""]}\n```', [5])
    assert out == [{"fit_score": 55.0, "verdict": "ok", "sponsorship": "no", "dealbreakers": ["x"]}]


def test_batches_sized_by_tokens(monkeypatch):
    monkeypatch.setattr(ai_generator, "BATCH_PROMPT_TOKENS", 2000)
    short = [dict(id=i, title="t", description="x" * 100) for i in range(5)]
    long_ = [dict(id=10 + i, title="t", description="x" * 3000) for i in range(3)]
    batches = ai_generator.triage_batches({}, short + long_)
    assert [j["id"] for b in batches for j in b] == [0, 1, 2, 3, 4, 10, 11, 12]  # order kept
    assert len(batches[0]) >= 5 and all(len(b) == 1 for b in batches[1:])


# ── triage_jobs: batch → single fallback ─────────────────────────────────────

class FakeDB:
    commits = 0
    def commit(self): self.commits += 1


def _run_triage(monkeypatch, answer):
    """answer(ids) -> raw model text. Returns (jobs, stats, ids per call)."""
    calls = []

    async def fake_complete(prompt, *, tier):
        ids = [int(x) for x in re.findall(r"--- JOB id=(\d+) ---", prompt)]
        calls.append(ids)
        return answer(ids), "fake", "fake-model"
    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(llm, "configured", lambda: True)
    jobs = [_job(id=i, title=f"T{i}") for i in (1, 2, 3)]
    stats = asyncio.run(triage_jobs(FakeDB(), jobs, {}))
    return jobs, stats, calls


def test_misaligned_batch_falls_back_to_singles(monkeypatch):
    def answer(ids):
        if len(ids) > 1:   # batch: model drops a job and repeats another
            return json.dumps([_a(ids[0], 10), _a(ids[0], 10), _a(ids[1], 10)])
        return json.dumps([_a(ids[0], 60 + ids[0], f"job {ids[0]}")])
    jobs, stats, calls = _run_triage(monkeypatch, answer)
    assert calls == [[1, 2, 3], [1], [2], [3]]
    assert [j.ai_score for j in jobs] == [61, 62, 63]           # nothing from the bad batch
    assert [j.ai_verdict for j in jobs] == ["job 1", "job 2", "job 3"]
    assert [j.ai_model for j in jobs] == ["fake-model"] * 3
    assert stats == {"triaged": 3, "failed": 0, "skipped": 0, "error": None}


def test_malformed_batch_falls_back_and_counts_failures(monkeypatch):
    def answer(ids):
        if len(ids) > 1:
            return "Sure! Here are the assessments: [{"
        return "garbage" if ids == [2] else json.dumps([_a(ids[0], 50)])
    jobs, stats, _ = _run_triage(monkeypatch, answer)
    assert [j.ai_score for j in jobs] == [50, None, 50]
    assert stats["triaged"] == 2 and stats["failed"] == 1 and "not JSON" in stats["error"]


def test_triage_stops_on_daily_quota(monkeypatch):
    fake_providers(monkeypatch, "gemini")
    calls = []

    async def boom(p, prompt, timeout):
        calls.append(p.name)
        return resp(429, text='{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}')
    monkeypatch.setattr(llm, "_post", boom)

    db = FakeDB()
    stats = asyncio.run(triage_jobs(db, [_job(id=1), _job(id=2)], {"name": "H"}))
    assert db.commits == 0  # bailed on the first call, no partial writes claimed
    assert calls == ["gemini"]
    assert stats["skipped"] == 2 and stats["triaged"] == 0


def test_all_providers_erroring_is_reported(monkeypatch):
    fake_providers(monkeypatch, "groq")

    async def down(p, prompt, timeout):
        return resp(500)
    monkeypatch.setattr(llm, "_post", down)
    stats = asyncio.run(triage_jobs(FakeDB(), [_job(id=1), _job(id=2)], {}))
    assert stats["triaged"] == 0 and stats["failed"] == 2
    assert "groq" in stats["error"]


def test_retry_after_parsing():
    from llm import _retry_after
    google_err = ('429 Quota exceeded ... retry_delay {\n  seconds: 47\n}\n')
    assert _retry_after(Exception(google_err)) == 48.0          # seconds + 1
    assert _retry_after(Exception("please retry in 5.5s")) == 6.5
    assert _retry_after(Exception("no hint")) == 20.0           # default
    assert _retry_after(Exception("retry_delay { seconds: 999 }")) == 65.0  # capped
    assert _retry_after("", {"retry-after": "2"}) == 3.0         # Groq header
    assert _retry_after("", {"x-ratelimit-reset-tokens": "7.66s",
                             "x-ratelimit-reset-requests": "120ms"}) == 8.66


def test_scan_and_single_triage_share_one_loop(monkeypatch, tmp_path):
    """Phase 0: a scan's triage and a single-job triage contend for the same
    module-level asyncio.Lock (now llm's per-provider lock). On one loop that's
    fine; across loops it raised 'bound to a different event loop'.
    Phase 2: the scan triages every new job and reports the counts."""
    import scan_service, user_settings
    from routes import jobs as jobs_route

    fake_providers(monkeypatch, "groq", rpm=600)  # 0.1s spacing -> the lock is contended

    async def slow_ok(p, prompt, timeout):
        await asyncio.sleep(0.05)
        ids = [int(x) for x in re.findall(r"--- JOB id=(\d+) ---", prompt)]
        return resp(200, json={"choices": [{"message": {"content": json.dumps([_a(i) for i in ids])}}]})
    monkeypatch.setattr(llm, "_post", slow_ok)

    profile = tmp_path / "profile.json"
    profile.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(jobs_route, "settings", SimpleNamespace(profile_path=profile))
    monkeypatch.setattr(scan_service, "_load_profile", lambda: {})
    monkeypatch.setattr(user_settings, "load", lambda: {"search_terms": [], "locations": [], "max_jobs_per_scan": 5})

    async def fake_scrape(**_):
        return [dict(title=f"T{i}", company="C", location="L", url=f"https://x/{i}") for i in range(12)]

    async def noop(_jobs):
        pass
    monkeypatch.setattr(scan_service, "scrape_all", fake_scrape)
    monkeypatch.setattr(scan_service, "enrich_keejob_details", noop)

    factory = _memory_db()
    db = factory()
    db.add(Job(url="https://x/existing", title="Old", company="C"))
    db.commit()
    job_id = db.query(Job).first().id

    async def both():
        return await asyncio.gather(
            scan_service.scan_and_store(factory),
            jobs_route.triage_one(job_id, db),
        )
    ids, out = asyncio.run(both())  # any loop-binding error propagates here
    assert len(ids) == 12
    assert out["fit_score"] == 50.0 and out["assessed"]
    st = scan_service.get_scan_state()
    assert (st["triaged"], st["failed"], st["skipped"]) == (12, 0, 0)  # all of them, not a top 10
    assert factory().query(Job).filter(Job.ai_score.is_(None)).count() == 0
