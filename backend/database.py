import datetime
import hashlib
import re
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, create_engine, func,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    company = Column(String)
    location = Column(String)
    description = Column(Text)
    # url stays UNIQUE. Two sources can legally hand us the same apply link,
    # but the scan matches on url before content_key and never inserts a url
    # it has already seen (in the DB or earlier in the batch) — the second
    # sighting lands in also_seen, so the constraint is a backstop that can't
    # fire mid-scan. Dropping it would also need a full SQLite table rebuild.
    url = Column(String, unique=True)
    # Cross-source identity: sha1 of normalized title|company|country.
    # Indexed, not unique — rows stored before dedup may already share a key.
    content_key = Column(String, index=True)
    also_seen = Column(Text, default="[]")  # JSON [[source, url], ...] of duplicate sightings
    source = Column(String)          # linkedin | indeed | glassdoor | keejob | ...
    job_type = Column(String)        # full-time | internship | remote
    date_posted = Column(String)
    salary = Column(String)
    match_score = Column(Float, default=0.0)  # keyword hint: only orders which jobs get triaged first — never shown
    match_reasons = Column(Text)     # JSON array
    status = Column(String, default="new")   # new | saved | applied | interview | offer | rejected
    is_applied = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.datetime.utcnow, index=True)  # bumped every scan the URL still appears

    # ── LLM triage (nullable = not yet assessed) ─────────────────────────────
    ai_score = Column(Float)                      # realistic fit 0-100
    ai_verdict = Column(String, default="")       # one-line human summary
    sponsorship = Column(String, default="")     # yes | likely | unclear | no
    dealbreakers = Column(Text, default="[]")     # JSON array of hard blockers
    ai_assessed_at = Column(DateTime)
    ai_provider = Column(String)                  # groq | gemini | openrouter — who wrote the verdict
    ai_model = Column(String)
    triage_version = Column(Integer)              # ai_generator.TRIAGE_VERSION at assessment; NULL = pre-versioning

    @hybrid_property
    def fit_score(self):
        """THE score the user sees — in the jobs list, stats and digest alike.
        None/NULL = pending AI check; never falls back to match_score.
        Works on a row (j.fit_score) and in SQL (Job.fit_score)."""
        return self.ai_score


# Trailing noise aggregators bolt onto the same title: "(m/f/d)", "(all genders)",
# "- Remote", "| Hybrid". Stripped repeatedly, so "X (m/w/d) - Remote" → "x".
_TITLE_SUFFIX = re.compile(
    r"\s*(?:[(\[]\s*(?:[mfwhdx]\s*/\s*)+[mfwhdx]\s*[)\]]"
    r"|[(\[]\s*all genders\s*[)\]]"
    r"|[-–—|,:/]?\s*[(\[]?\s*(?:remote|hybrid|on-?site)\s*[)\]]?)\s*$"
)


def _norm(s: str) -> str:
    return " ".join((s or "").casefold().split())


def content_key(title: str, company: str, location: str) -> str:
    """Same posting, any source. Country = last comma part of location, so
    "Barcelona, Spain" and "Spain" match; "Tunis" vs "Tunis, Tunisia" won't
    (a missed merge, never a wrong one)."""
    t = _norm(title)
    while (stripped := _TITLE_SUFFIX.sub("", t)) != t:
        t = stripped
    country = _norm((location or "").rsplit(",", 1)[-1])
    return hashlib.sha1(f"{t}|{_norm(company)}|{country}".encode()).hexdigest()


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), unique=True)
    cv_path = Column(String)
    cover_letter_path = Column(String)
    email_subject = Column(String)
    email_body = Column(Text)
    email_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime)
    response_status = Column(String, default="pending")   # pending | interview | offer | rejected
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


def create_tables():
    Base.metadata.create_all(bind=engine)
    # create_all skips existing tables — add columns added after first run by hand
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(jobs)")}
        if "last_seen" not in cols:
            conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN last_seen DATETIME")
            conn.exec_driver_sql("UPDATE jobs SET last_seen = created_at")
        for col, ddl in [
            ("ai_score", "ai_score FLOAT"),
            ("ai_verdict", "ai_verdict VARCHAR DEFAULT ''"),
            ("sponsorship", "sponsorship VARCHAR DEFAULT ''"),
            ("dealbreakers", "dealbreakers TEXT DEFAULT '[]'"),
            ("ai_assessed_at", "ai_assessed_at DATETIME"),
            ("ai_provider", "ai_provider VARCHAR"),
            ("ai_model", "ai_model VARCHAR"),
            ("triage_version", "triage_version INTEGER"),
        ]:
            if col not in cols:
                conn.exec_driver_sql(f"ALTER TABLE jobs ADD COLUMN {ddl}")
        if "content_key" not in cols:
            conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN content_key VARCHAR")
        if "also_seen" not in cols:
            conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN also_seen TEXT DEFAULT '[]'")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_jobs_content_key ON jobs (content_key)")
        # Backfill. Existing duplicates keep their own rows (they may carry
        # applications); new sightings just merge into whichever comes first.
        todo = conn.exec_driver_sql(
            "SELECT id, title, company, location FROM jobs WHERE content_key IS NULL").fetchall()
        for id_, title, company, location in todo:
            conn.exec_driver_sql("UPDATE jobs SET content_key = ? WHERE id = ?",
                                 (content_key(title, company, location), id_))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# A job is "fresh" if it was seen within this window of the most recent scan.
# A full scan spans a few minutes, so 12h comfortably covers one batch.
# ponytail: if a scan partially fails (e.g. RapidAPI quota out) only the sources
# that ran get re-stamped and the rest drop off — widen this if that bites.
FRESH_WINDOW = datetime.timedelta(hours=12)


def fresh_jobs(db: Session):
    """Query of jobs from the latest scan, plus anything the user is tracking."""
    q = db.query(Job)
    newest = db.query(func.max(Job.last_seen)).scalar()
    if newest:
        cutoff = newest - FRESH_WINDOW
        q = q.filter((Job.last_seen >= cutoff) | (Job.status != "new") | Job.is_applied)
    return q
