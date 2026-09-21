"""Phase 3: per-source budgets, failure isolation, full term coverage."""
import asyncio

import pytest

from sources import base, budget_for, fetch_all, keejob
from sources.base import Source, SourceError, combos
from sources.jsearch import _country_code
from sources.keejob import KEEJOB_TERMS, KeejobSource

TERMS = ["Software Engineer", "Full Stack Developer", "Web Developer", "Flutter Developer",
         "React Developer", "Angular Developer", "Python Developer",
         "Software Engineering Intern", "Web Development Intern"]
LOCS = ["Barcelona, Spain", "Spain", "Canada", "Netherlands", "Germany",
        "Ireland", "Remote", "France", "Portugal", "United Kingdom"]


@pytest.fixture(autouse=True)
def isolated_cursors(monkeypatch, tmp_path):
    monkeypatch.setattr(base, "CURSOR_PATH", tmp_path / "source_cursors.json")


class Fake(Source):
    """Round-robins terms × locations like a real source; returns `per_query`
    distinct jobs per query, tagged with its name."""

    def __init__(self, name, queries=3, per_query=100, fail=None):
        self.name, self.queries, self.per_query, self.fail = name, queries, per_query, fail
        self.budget, self.queried = None, []

    async def fetch(self, terms, locations, budget):
        self.budget = budget
        if self.fail:
            raise self.fail
        plan = base.take(self.name, combos(terms, locations), self.queries)
        base.advance(self.name, len(plan))
        self.queried += plan
        return [{"url": f"https://{self.name}/{t}/{l}/{k}", "source": self.name}
                for t, l in plan for k in range(self.per_query)]


def run(sources, total=50):
    return asyncio.run(fetch_all(sources, TERMS, LOCS, total))


def test_each_source_gets_its_budget():
    srcs = [Fake("a"), Fake("b"), Fake("c")]
    out = run(srcs, total=50)
    assert [s.budget for s in srcs] == [17, 17, 16]  # sums to max_jobs_per_scan, no more
    # a source that returns far more than its share is cut to it, so the first
    # source can never eat the later ones' allocation (the old all_jobs[:limit])
    assert [len(r) for _, r in out] == [17, 17, 16]
    assert all(j["source"] == s.name for s, r in out for j in r)
    assert sum(budget_for(i, 7, 200) for i in range(7)) == 200


def test_failing_source_does_not_drop_others():
    broken = Fake("jsearch", fail=SourceError("403 — key not subscribed"))
    ok = Fake("keejob")
    out = dict(run([broken, ok], total=20))
    assert isinstance(out[broken], SourceError) and "403" in str(out[broken])
    assert len(out[ok]) == 10


def test_every_term_queried_across_scans():
    # 10 locations, only 3 queries a scan: the old terms[:2] never got past
    # "Full Stack Developer". Now each scan picks up where the last stopped.
    src = Fake("jsearch", queries=3)
    for _ in range(3):
        run([src])
    assert {t for t, _ in src.queried} == set(TERMS)
    assert len({l for _, l in src.queried}) == 9  # and locations spread too
    # ... and the whole grid, eventually
    for _ in range(len(TERMS) * len(LOCS) // 3):
        run([src])
    assert set(src.queried) == {(t, l) for t in TERMS for l in LOCS}


def test_combos_cover_grid_once():
    pairs = combos(TERMS, LOCS)
    assert len(pairs) == len(set(pairs)) == len(TERMS) * len(LOCS)
    assert pairs[:2] == [(TERMS[0], LOCS[0]), (TERMS[1], LOCS[1])]


def test_country_code():
    assert _country_code("Barcelona, Spain") == "es"
    assert _country_code("Spain") == "es"
    assert _country_code("Toronto, Canada") == "ca"
    assert _country_code("Amsterdam, Netherlands") == "nl"
    assert _country_code("Atlantis") is None


def fake_keejob(monkeypatch, failing=()):
    async def scrape(term):
        if term in failing:
            raise ValueError("no job cards parsed")
        return [{"url": f"https://keejob/{term}/{k}", "term": term} for k in range(10)]
    monkeypatch.setattr(keejob, "scrape_keejob", scrape)


def test_keejob_keeps_every_term_under_budget(monkeypatch):
    # 6 terms × 10 cards cut to 25: merged in term order, the cut kept only the
    # first 3 terms — "web", "mobile", "stage informatique" never got through
    fake_keejob(monkeypatch)
    jobs = asyncio.run(KeejobSource().fetch([], [], 25))
    assert len(jobs) == 25
    assert {j["term"] for j in jobs} == set(KEEJOB_TERMS)


def test_keejob_every_term_failing_raises(monkeypatch):
    fake_keejob(monkeypatch, failing=KEEJOB_TERMS)
    with pytest.raises(SourceError):
        asyncio.run(KeejobSource().fetch([], [], 25))


def test_keejob_one_term_failing_is_skipped(monkeypatch):
    fake_keejob(monkeypatch, failing={"web"})
    jobs = asyncio.run(KeejobSource().fetch([], [], 100))
    assert len(jobs) == 50
    assert {j["term"] for j in jobs} == set(KEEJOB_TERMS) - {"web"}
