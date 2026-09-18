"""
/jobs endpoints
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from sqlalchemy import func

import llm
from config import settings
from database import Application, Job, fresh_jobs, get_db
from ai_generator import generate_cv_data, generate_cover_letter, generate_email
from pdf_builder import build_cv_pdf, build_cover_letter_pdf

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger("jobs")

# The loop only weakly references tasks — hold them here until they finish or
# they can be garbage-collected mid-flight.
_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    def _done(t: asyncio.Task):
        _tasks.discard(t)
        if not t.cancelled() and t.exception():
            logger.error(f"❌ Background task failed: {t.exception()!r}")

    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_done)


# ── Pydantic response schemas ─────────────────────────────────────────────────

class JobOut(BaseModel):
    id: int
    title: str
    company: str
    location: str
    url: str
    source: str
    job_type: str
    date_posted: str
    salary: str
    match_score: float
    match_reasons: List[str]
    status: str
    is_applied: bool
    ai_score: Optional[float] = None
    ai_verdict: str = ""
    sponsorship: str = ""
    dealbreakers: List[str] = []

    class Config:
        from_attributes = True


class JobDetail(JobOut):
    description: str


def _json_list(raw: str) -> list:
    try:
        v = json.loads(raw or "[]")
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _job_out(j: Job) -> dict:
    return {
        "id": j.id,
        "title": j.title or "",
        "company": j.company or "",
        "location": j.location or "",
        "url": j.url or "",
        "source": j.source or "",
        "job_type": j.job_type or "",
        "date_posted": j.date_posted or "",
        "salary": j.salary or "",
        "match_score": j.match_score or 0.0,
        "match_reasons": _json_list(j.match_reasons),
        "status": j.status or "new",
        "is_applied": j.is_applied or False,
        "ai_score": j.ai_score,
        "ai_verdict": j.ai_verdict or "",
        "sponsorship": j.sponsorship or "",
        "dealbreakers": _json_list(j.dealbreakers),
        "description": j.description or "",
    }


# ── GET /jobs ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[JobOut])
def list_jobs(
    source: Optional[str] = None,
    status: Optional[str] = None,
    min_score: float = 0,
    location: Optional[str] = None,
    sponsorship: Optional[str] = None,
    include_stale: bool = False,
    db: Session = Depends(get_db),
):
    # rank by the Gemini fit score when we have one, else the keyword score
    effective = func.coalesce(Job.ai_score, Job.match_score)
    q = db.query(Job) if include_stale else fresh_jobs(db)
    if source:
        q = q.filter(Job.source == source)
    if status:
        q = q.filter(Job.status == status)
    if min_score:
        q = q.filter(effective >= min_score)
    if location:
        q = q.filter(Job.location.ilike(f"%{location}%"))
    if sponsorship:
        wanted = [s.strip() for s in sponsorship.split(",") if s.strip()]
        q = q.filter(Job.sponsorship.in_(wanted))
    jobs = q.order_by(effective.desc()).all()
    return [_job_out(j) for j in jobs]


# ── GET /jobs/{id} ────────────────────────────────────────────────────────────

@router.get("/{job_id:int}", response_model=JobDetail)
def get_job(job_id: int, db: Session = Depends(get_db)):
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(404, "Job not found")
    return _job_out(j)


# ── PATCH /jobs/{id}/status ───────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: str

@router.patch("/{job_id:int}/status")
def update_status(job_id: int, body: StatusUpdate, db: Session = Depends(get_db)):
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(404, "Job not found")
    j.status = body.status
    db.commit()
    return {"ok": True}


# ── POST /jobs/{id}/mark-applied ──────────────────────────────────────────────

@router.post("/{job_id:int}/mark-applied")
def mark_applied(job_id: int, db: Session = Depends(get_db)):
    """Toggle is_applied for jobs applied to outside the app (most of them, in
    practice). Also gets it into the Applications tracker like the automated
    /apply flow does, so response status (interview/offer/...) can be logged
    the same way — minus a generated CV, since none was made for this job."""
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(404, "Job not found")

    j.is_applied = not j.is_applied
    if j.is_applied:
        j.status = "applied"
        if not db.query(Application).filter(Application.job_id == job_id).first():
            db.add(Application(job_id=job_id, response_status="pending"))
    elif j.status == "applied":
        j.status = "new"

    db.commit()
    return _job_out(j)


# ── POST /jobs/{id}/triage ────────────────────────────────────────────────────

@router.post("/{job_id:int}/triage")
async def triage_one(job_id: int, db: Session = Depends(get_db)):
    """Run (or re-run) the AI fit + sponsorship check on a single job."""
    from scan_service import _apply_triage
    from ai_generator import triage_job

    # Sync SQLAlchemy inside async endpoints runs on the event loop — deliberate:
    # local SQLite queries are sub-millisecond, not worth a thread hop.
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(404, "Job not found")
    with open(settings.profile_path, encoding="utf-8") as f:
        profile = json.load(f)

    try:
        result = await triage_job(profile, _job_out(j))
    except llm.AllProvidersExhausted:
        raise HTTPException(503, "Every LLM provider is out of quota for today.")
    if not _apply_triage(j, result):
        raise HTTPException(502, "The LLM returned nothing usable — check your API keys.")
    db.commit()
    return _job_out(j)


# ── POST /jobs/triage-pending ─────────────────────────────────────────────────

async def _triage_pending(session_factory, limit: int):
    """Background task: triage fresh jobs that were never assessed."""
    from database import fresh_jobs
    from scan_service import triage_jobs

    db = session_factory()
    try:
        with open(settings.profile_path, encoding="utf-8") as f:
            profile = json.load(f)
        pending = (
            fresh_jobs(db)
            .filter(Job.ai_assessed_at.is_(None))
            .order_by(func.coalesce(Job.ai_score, Job.match_score).desc())
            .limit(limit)
            .all()
        )
        await triage_jobs(db, pending, profile)
        db.commit()
    finally:
        db.close()


@router.post("/triage-pending")
async def triage_pending(limit: int = 25, db: Session = Depends(get_db)):
    """Kick off AI triage for fresh jobs that haven't been assessed yet.
    Rate-limited per provider, so it runs in the background."""
    from database import SessionLocal, fresh_jobs

    n = fresh_jobs(db).filter(Job.ai_assessed_at.is_(None)).count()
    if not n:
        return {"message": "All fresh jobs already assessed."}
    take = min(n, limit)
    _spawn(_triage_pending(SessionLocal, limit))
    return {"message": f"Assessing {take} of {n} pending job(s) in the background. Refresh to see results."}


# ── POST /jobs/scan ───────────────────────────────────────────────────────────

@router.post("/scan")
async def trigger_scan():
    from database import SessionLocal
    from scan_service import get_scan_state, scan_and_store

    if get_scan_state()["running"]:
        return {"message": "A scan is already running"}
    _spawn(scan_and_store(SessionLocal))
    return {"message": "Scan started in background"}


@router.get("/scan-status")
def scan_status():
    """Poll this while a scan is running — scrape + triage can take minutes,
    way past any fixed-timeout guess, so the frontend polls instead of waiting
    a fixed number of seconds and hoping it's done."""
    from scan_service import get_scan_state
    return get_scan_state()


# ── POST /jobs/{id}/generate ──────────────────────────────────────────────────

@router.post("/{job_id:int}/generate")
async def generate_documents(job_id: int, db: Session = Depends(get_db)):
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(404, "Job not found")

    with open(settings.profile_path, encoding="utf-8") as f:
        profile = json.load(f)

    job_dict = _job_out(j)

    try:
        cv_data = await generate_cv_data(profile, job_dict)
        cl_text = await generate_cover_letter(profile, job_dict, cv_data)
    except llm.AllProvidersExhausted:
        raise HTTPException(503, "Every LLM provider is out of quota for today.")
    except llm.LLMError as exc:
        raise HTTPException(502, f"LLM call failed: {exc}")
    subject, body = await generate_email(profile, job_dict, cl_text)

    # Build PDFs — ReportLab is CPU-bound, keep it off the loop
    slug = f"job_{job_id}"
    cv_path = settings.generated_dir / f"CV_{slug}.pdf"
    cl_path = settings.generated_dir / f"CL_{slug}.pdf"
    await asyncio.to_thread(build_cv_pdf, profile, cv_data, cv_path)
    await asyncio.to_thread(build_cover_letter_pdf, profile, job_dict, cl_text, cl_path)

    # Persist / update application record
    app = db.query(Application).filter(Application.job_id == job_id).first()
    if not app:
        app = Application(job_id=job_id)
        db.add(app)
    app.cv_path = str(cv_path)
    app.cover_letter_path = str(cl_path)
    app.email_subject = subject
    app.email_body = body
    db.commit()

    return {
        "cv_path": str(cv_path),
        "cover_letter_path": str(cl_path),
        "email_subject": subject,
        "email_preview": body[:500],
        "cv_summary": cv_data.get("summary", ""),
    }


# ── POST /jobs/{id}/apply ─────────────────────────────────────────────────────

class ApplyRequest(BaseModel):
    to_email: str

@router.post("/{job_id:int}/apply")
def apply_to_job(job_id: int, body: ApplyRequest, db: Session = Depends(get_db)):
    import datetime
    from email_sender import send_application

    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(404, "Job not found")

    app = db.query(Application).filter(Application.job_id == job_id).first()
    if not app or not app.email_body:
        raise HTTPException(400, "Generate documents first before applying.")

    try:
        send_application(
            to_email=body.to_email,
            subject=app.email_subject,
            body=app.email_body,
            cv_path=Path(app.cv_path) if app.cv_path else None,
            cover_letter_path=Path(app.cover_letter_path) if app.cover_letter_path else None,
        )
    except Exception as exc:
        raise HTTPException(500, f"Email failed: {exc}")

    app.email_sent = True
    app.sent_at = datetime.datetime.utcnow()
    j.is_applied = True
    j.status = "applied"
    db.commit()
    return {"message": "Application sent successfully!"}
