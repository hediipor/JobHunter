"""Phase 4: the same posting from two sources is one row, with both urls recorded."""
import asyncio
import json

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import scan_service
import user_settings
from database import Base, Job, content_key
from sources.base import Source


def _memory_db():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)


def _source(name, job):
    class S(Source):
        async def fetch(self, terms, locations, budget):
            return [dict(job)]
    S.name = name
    return S()


def test_content_key_survives_noise():
    k = content_key("Backend Engineer", "Acme", "Berlin, Germany")
    assert content_key("  backend   ENGINEER (m/f/d) - Remote ", "ACME ", "Germany") == k
    assert content_key("Backend Engineer (all genders)", "acme", "Munich,  germany") == k
    assert content_key("Backend Engineer | Hybrid", "Acme", "Germany") == k
    assert content_key("Backend Engineer (Python)", "Acme", "Germany") != k  # real qualifiers stay
    assert content_key("Backend Engineer", "Acme", "Spain") != k


def test_same_posting_two_sources_one_row(monkeypatch):
    a = dict(title="Backend Engineer", company="Acme", location="Berlin, Germany",
             url="https://linkedin.example/jobs/1", source="linkedin")
    b = dict(title="  backend  engineer ", company="ACME", location="Germany",
             url="https://hiring.cafe/job/xyz", source="hiringcafe")

    monkeypatch.setattr(scan_service, "_load_profile", lambda: {})
    monkeypatch.setattr(user_settings, "load", lambda: {"search_terms": ["t"], "locations": ["l"],
                                                        "max_jobs_per_scan": 10, "sources": {}})
    monkeypatch.setattr(scan_service, "enabled_sources", lambda cfg: [_source("jsearch", a), _source("hc", b)])

    async def no_triage(db, rows, profile):
        return {"triaged": 0, "failed": 0, "skipped": 0, "error": None}
    monkeypatch.setattr(scan_service, "triage_jobs", no_triage)

    factory = _memory_db()
    ids = asyncio.run(scan_service.scan_and_store(factory))
    rows = factory().query(Job).all()
    assert len(ids) == len(rows) == 1
    assert rows[0].url == a["url"] and rows[0].source == "linkedin"
    assert json.loads(rows[0].also_seen) == [["hiringcafe", b["url"]]]

    # Next scan: both still listed → still one row, no duplicate pair, last_seen bumped.
    before = rows[0].last_seen
    assert asyncio.run(scan_service.scan_and_store(factory)) == []
    row = factory().query(Job).one()
    assert json.loads(row.also_seen) == [["hiringcafe", b["url"]]]
    assert row.last_seen > before


def test_create_tables_backfills_content_key(monkeypatch):
    eng = create_engine("sqlite://", poolclass=StaticPool)
    with eng.begin() as c:  # a pre-Phase-4 jobs table
        c.execute(text("CREATE TABLE jobs (id INTEGER PRIMARY KEY, title VARCHAR, company VARCHAR,"
                       " location VARCHAR, url VARCHAR UNIQUE, created_at DATETIME)"))
        c.execute(text("INSERT INTO jobs (title, company, location, url) VALUES ('Dev', 'Acme', 'Spain', 'u')"))
    monkeypatch.setattr(database, "engine", eng)
    database.create_tables()
    with eng.connect() as c:
        key, seen = c.execute(text("SELECT content_key, also_seen FROM jobs")).one()
    assert key == content_key("Dev", "Acme", "Spain") and seen == "[]"
