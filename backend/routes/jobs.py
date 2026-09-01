"""
/jobs endpoints
"""
import asyncio
import json
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import Application, Job, get_db
from ai_generator import generate_cv_data, generate_cover_letter, generate_email
from pdf_builder import build_cv_pdf, build_cover_letter_pdf

router = APIRouter(prefix="/jobs", tags=["jobs"])


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

    class Config:
        from_attributes = True


class JobDetail(JobOut):
    description: str


def _job_out(j: Job) -> dict:
    reasons = []
    try:
        reasons = json.loads(j.match_reasons or "[]")
    except Exception:
        pass
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
        "match_reasons": reasons,
        "status": j.status or "new",
        "is_applied": j.is_applied or False,
        "description": j.description or "",
    }


# ── GET /jobs ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[JobOut])
def list_jobs(
    source: Optional[str] = None,
    status: Optional[str] = None,
    min_score: float = 0,
    location: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Job)
    if source:
        q = q.filter(Job.source == source)
    if status:
        q = q.filter(Job.status == status)
    if min_score:
        q = q.filter(Job.match_score >= min_score)
    if location:
        q = q.filter(Job.location.ilike(f"%{location}%"))
    jobs = q.order_by(Job.match_score.desc()).all()
    return [_job_out(j) for j in jobs]


# ── GET /jobs/{id} ────────────────────────────────────────────────────────────

@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, db: Session = Depends(get_db)):
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(404, "Job not found")
    return _job_out(j)


# ── PATCH /jobs/{id}/status ───────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: str

@router.patch("/{job_id}/status")
def update_status(job_id: int, body: StatusUpdate, db: Session = Depends(get_db)):
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(404, "Job not found")
    j.status = body.status
    db.commit()
    return {"ok": True}


# ── POST /jobs/scan ───────────────────────────────────────────────────────────

def _do_scan(db_session_factory):
    """Background task: run the shared scan pipeline."""
    from scan_service import scan_and_store
    return asyncio.run(scan_and_store(db_session_factory))


@router.post("/scan")
def trigger_scan(background_tasks: BackgroundTasks):
    from database import SessionLocal
    background_tasks.add_task(_do_scan, SessionLocal)
    return {"message": "Scan started in background"}


# ── POST /jobs/{id}/generate ──────────────────────────────────────────────────

@router.post("/{job_id}/generate")
def generate_documents(job_id: int, db: Session = Depends(get_db)):
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(404, "Job not found")

    with open(settings.profile_path, encoding="utf-8") as f:
        profile = json.load(f)

    job_dict = _job_out(j)

    async def _gen():
        cv_data = await generate_cv_data(profile, job_dict)
        cl_text = await generate_cover_letter(profile, job_dict, cv_data)
        subject, body = await generate_email(profile, job_dict, cl_text)
        return cv_data, cl_text, subject, body

    cv_data, cl_text, subject, body = asyncio.run(_gen())

    # Build PDFs
    slug = f"job_{job_id}"
    cv_path = settings.generated_dir / f"CV_{slug}.pdf"
    cl_path = settings.generated_dir / f"CL_{slug}.pdf"
    build_cv_pdf(profile, cv_data, cv_path)
    build_cover_letter_pdf(profile, job_dict, cl_text, cl_path)

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

@router.post("/{job_id}/apply")
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
