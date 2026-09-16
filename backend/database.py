import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, create_engine, func,
)
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
    url = Column(String, unique=True)
    source = Column(String)          # linkedin | indeed | glassdoor | keejob | ...
    job_type = Column(String)        # full-time | internship | remote
    date_posted = Column(String)
    salary = Column(String)
    match_score = Column(Float, default=0.0)
    match_reasons = Column(Text)     # JSON array
    status = Column(String, default="new")   # new | saved | applied | interview | offer | rejected
    is_applied = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.datetime.utcnow, index=True)  # bumped every scan the URL still appears

    # ── Gemini triage (nullable = not yet assessed) ──────────────────────────
    ai_score = Column(Float)                      # realistic fit 0-100
    ai_verdict = Column(String, default="")       # one-line human summary
    sponsorship = Column(String, default="")     # yes | likely | unclear | no
    dealbreakers = Column(Text, default="[]")     # JSON array of hard blockers
    ai_assessed_at = Column(DateTime)


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
        ]:
            if col not in cols:
                conn.exec_driver_sql(f"ALTER TABLE jobs ADD COLUMN {ddl}")


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
