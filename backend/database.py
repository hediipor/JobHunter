import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, create_engine,
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
