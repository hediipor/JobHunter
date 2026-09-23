"""
/jobs endpoints
"""
import asyncio
import datetime
import json
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
    match_reasons: List[str]
    status: str
    is_applied: bool
    fit_score: Optional[float] = None   # the only score shown; None = pending AI check
    assessed: bool = False
    ai_provider: str = ""
    ai_model: str = ""
    ai_verdict: str = ""
    sponsorship: str = ""
    dealbreakers: List[str] = []
    also_seen: List[dict] = []          # [{source, url}] — same posting on other boards
    feedback: Optional[int] = None      # 1 = good fit, -1 = not a fit, None = not rated
    feedback_reason: str = ""

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
        "match_reasons": _json_list(j.match_reasons),
        "status": j.status or "new",
        "is_applied": j.is_applied or False,
        "fit_score": j.fit_score,
        "assessed": j.fit_score is not None,
        "ai_provider": j.ai_provider or "",
        "ai_model": j.ai_model or "",
        "ai_verdict": j.ai_verdict or "",
        "sponsorship": j.sponsorship or "",
        "dealbreakers": _json_list(j.dealbreakers),
        "also_seen": [{"source": p[0], "url": p[1]} for p in _json_list(j.also_seen) if len(p) == 2],
        "feedback": j.feedback,
        "feedback_reason": j.feedback_reason or "",
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
    q = db.query(Job) if include_stale else fresh_jobs(db)
    if source:
        q = q.filter(Job.source == source)
    if status:
        q = q.filter(Job.status == status)
    if min_score:
        q = q.filter(Job.fit_score >= min_score)  # pending jobs have no score to pass
    if location:
        q = q.filter(Job.location.ilike(f"%{location}%"))
    if sponsorship:
        wanted = [s.strip() for s in sponsorship.split(",") if s.strip()]
        q = q.filter(Job.sponsorship.in_(wanted))
    # assessed first by fit; pending after, in the order they'll be triaged
    jobs = q.order_by(Job.fit_score.desc().nulls_last(), Job.match_score.desc()).all()
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


# ── PATCH /jobs/{id}/feedback ─────────────────────────────────────────────────

class FeedbackUpdate(BaseModel):
    feedback: int          # 1 = good fit, -1 = not a fit, 0 = clear (back to NULL)
    reason: Optional[str] = None   # short free text, mainly for 👎

@router.patch("/{job_id:int}/feedback")
def update_feedback(job_id: int, body: FeedbackUpdate, db: Session = Depends(get_db)):
    if body.feedback not in (1, -1, 0):
        raise HTTPException(400, "feedback must be 1, -1 or 0")
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(404, "Job not found")
    if body.feedback == 0:
        j.feedback, j.feedback_reason = None, None
    else:
        j.feedback = body.feedback
        j.feedback_reason = ((body.reason or "").strip()[:200]) or None
    db.commit()
    return _job_out(j)


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
    else:
        if j.status == "applied":
            j.status = "new"
        # drop the bare tracker row from toggle-on — but never one with a CV,
        # an email, a sent mail, a logged response or notes on it
        app = db.query(Application).filter(Application.job_id == job_id).first()
        if app and not (app.cv_path or app.cover_letter_path or app.email_body or app.email_sent
                        or app.notes or app.response_status not in (None, "pending")):
            db.delete(app)

    db.commit()
    return _job_out(j)


# ── POST /jobs/{id}/triage ────────────────────────────────────────────────────

@router.post("/{job_id:int}/triage")
async def triage_one(job_id: int, db: Session = Depends(get_db)):
    """Run (or re-run) the AI fit + sponsorship check on a single job."""
    from scan_service import _apply_triage, _job_dict
    from ai_generator import TriageParseError, triage_batch

    # Sync SQLAlchemy inside async endpoints runs on the event loop — deliberate:
    # local SQLite queries are sub-millisecond, not worth a thread hop.
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(404, "Job not found")
    with open(settings.profile_path, encoding="utf-8") as f:
        profile = json.load(f)

    try:
        [result], provider, model = await triage_batch(profile, [_job_dict(j)])
    except llm.AllProvidersExhausted:
        raise HTTPException(503, "Every LLM provider is out of quota for today.")
    except (llm.LLMError, TriageParseError) as exc:
        raise HTTPException(502, f"AI check failed: {exc}")
    _apply_triage(j, result, provider, model)
    db.commit()
    return _job_out(j)


# ── POST /jobs/triage-pending ─────────────────────────────────────────────────

async def _triage_pending(session_factory, limit: int):
    """Background task: triage fresh jobs that were never assessed."""
    from database import fresh_jobs
    from scan_service import _triage_state, triage_jobs

    db = session_factory()
    t = {"triaged": None, "failed": None, "skipped": None, "error": None}
    try:
        with open(settings.profile_path, encoding="utf-8") as f:
            profile = json.load(f)
        pending = (
            fresh_jobs(db)
            .filter(Job.ai_assessed_at.is_(None))
            .order_by(Job.match_score.desc())  # keyword hint: likeliest fits first
            .limit(limit)
            .all()
        )
        t = await triage_jobs(db, pending, profile)
        db.commit()
    except Exception as exc:
        t["error"] = str(exc)
        raise
    finally:
        db.close()
        _triage_state.update(t, running=False, finished_at=datetime.datetime.now(datetime.UTC).isoformat())


@router.post("/triage-pending")
async def triage_pending(limit: int = 25, db: Session = Depends(get_db)):
    """Kick off AI triage for fresh jobs that haven't been assessed yet.
    Rate-limited per provider, so it runs in the background."""
    from database import SessionLocal, fresh_jobs
    from scan_service import _triage_state

    if _triage_state["running"]:
        return {"started": False, "message": "An AI check is already running."}
    n = fresh_jobs(db).filter(Job.ai_assessed_at.is_(None)).count()
    if not n:
        return {"started": False, "message": "All fresh jobs already assessed."}
    take = min(n, limit)
    _triage_state.update(running=True, finished_at=None, triaged=None, failed=None, skipped=None, error=None)
    _spawn(_triage_pending(SessionLocal, limit))
    return {"started": True, "message": f"Assessing {take} of {n} pending job(s) in the background."}


@router.get("/triage-status")
def triage_status():
    """Poll after POST /triage-pending; running=false means the counts are final."""
    from scan_service import get_triage_state
    return get_triage_state()


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
    from email_sender import send_application

    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(404, "Job not found")

    app = db.query(Application).filter(Application.job_id == job_id).first()
    if not app or not app.email_body:
        raise HTTPException(400, "Generate documents first before applying.")

    try:
        with open(settings.profile_path, encoding="utf-8") as f:
            applicant_name = json.load(f).get("name", "")
        send_application(
            applicant_name=applicant_name,
            to_email=body.to_email,
            subject=app.email_subject,
            body=app.email_body,
            cv_path=Path(app.cv_path) if app.cv_path else None,
            cover_letter_path=Path(app.cover_letter_path) if app.cover_letter_path else None,
        )
    except Exception as exc:
        raise HTTPException(500, f"Email failed: {exc}")

    app.email_sent = True
    app.sent_at = datetime.datetime.now(datetime.UTC)
    j.is_applied = True
    j.status = "applied"
    db.commit()
    return {"message": "Application sent successfully!"}
