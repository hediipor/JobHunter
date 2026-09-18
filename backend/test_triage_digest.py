"""Self-checks for the AI-triage plumbing and the digest renderer.
No network: llm.complete / llm._post are monkeypatched."""
import asyncio
import json
from types import SimpleNamespace

from conftest import fake_providers, resp
from digest import render_digest, _score, STRONG_CUTOFF
from scan_service import _apply_triage


def _job(**kw):
    base = dict(id=1, title="Software Engineer", company="Acme", location="Barcelona, ES",
                url="https://x/y", match_score=40.0, ai_score=None, ai_verdict="",
                sponsorship="", dealbreakers="[]", description="")
    base.update(kw)
    return SimpleNamespace(**base)


def test_apply_triage():
    j = _job()
    ok = _apply_triage(j, {"fit_score": 71.0, "verdict": "Great new-grad fit",
                           "sponsorship": "likely", "dealbreakers": ["Requires German"]})
    assert ok
    assert j.ai_score == 71.0
    assert j.sponsorship == "likely"
    assert json.loads(j.dealbreakers) == ["Requires German"]
    assert j.ai_assessed_at is not None


def test_apply_triage_empty_result_is_noop():
    j = _job(ai_assessed_at=None)
    ok = _apply_triage(j, {"fit_score": None, "verdict": "", "sponsorship": "", "dealbreakers": []})
    assert not ok
    assert j.ai_assessed_at is None and j.sponsorship == ""


def test_score_fallback():
    assert _score(_job(ai_score=None, match_score=42.0)) == 42.0
    assert _score(_job(ai_score=88.0, match_score=42.0)) == 88.0


def test_render_digest_ranking_and_subject():
    jobs = [
        _job(id=1, ai_score=30.0),
        _job(id=2, ai_score=90.0, ai_verdict="Strong", sponsorship="yes"),
        _job(id=3, ai_score=None, match_score=70.0),
    ]
    subject, html = render_digest(jobs)
    assert "3 new job" in subject
    strong = [j for j in jobs if _score(j) >= STRONG_CUTOFF]  # ids 2,3
    assert f"{len(strong)} strong match" in subject
    # strong matches shown, highest first; the 30% one is held back
    assert html.index("90%") < html.index("70%")
    assert "30%" not in html
    assert "+ 1 more" in html
    assert "Strong" in html and "sponsors" in html.lower()


def test_render_digest_empty():
    assert render_digest([]) is None


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


def _ok_response(text):
    return resp(200, json={"choices": [{"message": {"content": text}}]})


def test_triage_stops_on_daily_quota(monkeypatch):
    import llm
    from scan_service import triage_jobs
    fake_providers(monkeypatch, "gemini")
    calls = []

    async def boom(p, prompt):
        calls.append(p.name)
        return resp(429, text='{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}')
    monkeypatch.setattr(llm, "_post", boom)

    class FakeDB:
        commits = 0
        def commit(self): self.commits += 1
    db = FakeDB()
    asyncio.run(triage_jobs(db, [_job(id=1), _job(id=2)], {"name": "H"}))
    assert db.commits == 0  # bailed on the first job, no partial writes claimed
    assert calls == ["gemini"]


def test_triage_job_parse(monkeypatch):
    import ai_generator, llm

    async def fake_complete(prompt, *, tier):
        assert tier == "fast"
        return ('```json\n{"fit_score": 55, "verdict": "ok", '
                '"sponsorship": "NO", "dealbreakers": ["x", ""]}\n```', "fake")
    monkeypatch.setattr(llm, "complete", fake_complete)
    out = asyncio.run(ai_generator.triage_job({"name": "H"}, _job().__dict__))
    assert out == {"fit_score": 55.0, "verdict": "ok", "sponsorship": "no", "dealbreakers": ["x"]}


def test_scan_and_single_triage_share_one_loop(monkeypatch, tmp_path):
    """Phase 0: a scan's triage and a single-job triage contend for the same
    module-level asyncio.Lock (now llm's per-provider lock). On one loop that's
    fine; across loops it raised 'bound to a different event loop'."""
    import llm, scan_service, user_settings
    from routes import jobs as jobs_route
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from database import Base, Job

    fake_providers(monkeypatch, "groq", rpm=600)  # 0.1s spacing -> the lock is contended

    async def slow_ok(p, prompt):
        await asyncio.sleep(0.05)
        return _ok_response('{"fit_score": 50, "verdict": "ok", "sponsorship": "no", "dealbreakers": []}')
    monkeypatch.setattr(llm, "_post", slow_ok)

    profile = tmp_path / "profile.json"
    profile.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(jobs_route, "settings", SimpleNamespace(profile_path=profile))
    monkeypatch.setattr(scan_service, "_load_profile", lambda: {})
    monkeypatch.setattr(user_settings, "load", lambda: {"search_terms": [], "locations": [], "max_jobs_per_scan": 5})

    async def fake_scrape(**_):
        return [dict(title=f"T{i}", company="C", location="L", url=f"https://x/{i}") for i in range(3)]

    async def noop(_jobs):
        pass
    monkeypatch.setattr(scan_service, "scrape_all", fake_scrape)
    monkeypatch.setattr(scan_service, "enrich_keejob_details", noop)

    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    factory = sessionmaker(bind=eng)
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
    assert len(ids) == 3
    assert out["ai_score"] == 50.0

