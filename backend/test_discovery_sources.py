"""Adzuna + Arbeitnow: mapping, ranking, budget, error handling (no network)."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from sources import adzuna, arbeitnow, base
from sources.adzuna import AdzunaSource
from sources.arbeitnow import ArbeitnowSource
from sources.base import SourceError, html_to_text, rank_by_terms


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(base, "CURSOR_PATH", tmp_path / "cursors.json")
    monkeypatch.setattr(adzuna, "settings", SimpleNamespace(
        adzuna_app_id="id", adzuna_app_key="key", profile_path=tmp_path / "none.json"))


def mock_http(monkeypatch, module, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def adz_item(n=1):
    return {"title": "Dev", "description": "<p>Build <b>things</b></p>", "created": "2026-09-29T10:00:00Z",
            "redirect_url": f"https://adzuna/{n}", "company": {"display_name": "Acme"},
            "location": {"display_name": "Gràcia, Barcelona", "area": ["España", "Cataluña", "Barcelona"]},
            "salary_min": 40000, "salary_max": 50000, "contract_time": "full_time"}


def test_adzuna_mapping_uses_queried_country(monkeypatch):
    seen = []
    def handler(req):
        seen.append(req.url.path)
        return httpx.Response(200, json={"results": [adz_item()]})
    mock_http(monkeypatch, adzuna, handler)
    [job] = asyncio.run(AdzunaSource().fetch(["Dev"], ["Barcelona, Spain"], 10))
    assert seen == ["/v1/api/jobs/es/search/1"]
    assert job["location"] == "Barcelona, ES"
    assert job["description"] == "Build things"
    assert job["job_type"] == "full-time" and job["date_posted"] == "2026-09-29"
    assert job["salary"] == "40,000 - 50,000" and job["source"] == "adzuna"


def test_adzuna_skips_unknown_country_and_remote_uses_home(monkeypatch):
    whats = []
    def handler(req):
        whats.append((req.url.path.split("/")[4], req.url.params["what"]))
        return httpx.Response(200, json={"results": []})
    mock_http(monkeypatch, adzuna, handler)
    asyncio.run(AdzunaSource().fetch(["Dev"], ["Atlantis", "Ireland", "Germany", "Remote"], 10))
    assert whats == [("de", "Dev"), ("de", "Dev remote")]


def test_adzuna_budget(monkeypatch):
    mock_http(monkeypatch, adzuna, lambda r: httpx.Response(200, json={"results": [adz_item(i) for i in range(50)]}))
    assert len(asyncio.run(AdzunaSource().fetch(["Dev"], ["Spain"], 7))) == 7


def test_adzuna_missing_key(monkeypatch):
    monkeypatch.setattr(adzuna.settings, "adzuna_app_key", "")
    with pytest.raises(SourceError):
        asyncio.run(AdzunaSource().fetch(["Dev"], ["Spain"], 7))


@pytest.mark.parametrize("status", [401, 429])
def test_adzuna_http_errors(monkeypatch, status):
    mock_http(monkeypatch, adzuna, lambda r: httpx.Response(status))
    with pytest.raises(SourceError):
        asyncio.run(AdzunaSource().fetch(["Dev"], ["Spain"], 7))


def arb_item(title, n, **kw):
    return {"slug": str(n), "company_name": "Co", "title": title, "description": "<p>Hi <i>there</i></p>",
            "remote": False, "url": f"https://arb/{n}", "tags": [], "job_types": ["Full-time"],
            "location": "Berlin", "created_at": 1790000000, **kw}


def test_arbeitnow_mapping_pages_and_ranking(monkeypatch):
    pages = {
        "1": {"data": [arb_item("Nurse", 1), arb_item("Frontend Engineer", 2, remote=True),
                       arb_item("Software Engineer", 3)], "links": {"next": "https://www.arbeitnow.com/api/job-board-api?page=2"}},
        "2": {"data": [arb_item("Engineer Intern", 4), arb_item("Chef", 5)], "links": {"next": "https://x?page=3"}},
    }
    hits = []
    def handler(req):
        hits.append(req.url.params.get("page", "1"))
        return httpx.Response(200, json=pages[hits[-1]])
    mock_http(monkeypatch, arbeitnow, handler)
    jobs = asyncio.run(ArbeitnowSource().fetch(["Software Engineer"], [], 10))
    assert hits == ["1", "2"]  # default 2 pages, never page 3
    assert [j["url"] for j in jobs] == ["https://arb/3", "https://arb/2", "https://arb/4"]  # 2 words, then feed order
    assert jobs[1]["location"] == "Remote" and jobs[0]["location"] == "Berlin"
    assert jobs[0]["description"] == "Hi there" and jobs[0]["job_type"] == "full-time"
    assert jobs[0]["date_posted"] == "2026-09-21" and jobs[0]["source"] == "arbeitnow"
    assert len(asyncio.run(ArbeitnowSource().fetch(["Software Engineer"], [], 2))) == 2


def test_rank_by_terms():
    items = ["Frontend Engineer", "Software Engineer", "Nurse", "Software"]
    assert rank_by_terms(items, ["Software Engineer"], str) == ["Software Engineer", "Frontend Engineer", "Software"]
    assert html_to_text("<p>a  <b>b</b>\n c</p>") == "a b c"
