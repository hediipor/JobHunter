"""
/applications endpoints — track application pipeline
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import Application, Job, get_db

router = APIRouter(prefix="/applications", tags=["applications"])


class AppOut(BaseModel):
    id: int
    job_id: int
    job_title: str
    company: str
    email_sent: bool
    response_status: str
    notes: str
    cv_path: str
    cover_letter_path: str
    email_subject: str

    class Config:
        from_attributes = True


def _app_out(a: Application, db: Session) -> dict:
    job = db.query(Job).filter(Job.id == a.job_id).first()
    return {
        "id": a.id,
        "job_id": a.job_id,
        "job_title": job.title if job else "",
        "company": job.company if job else "",
        "email_sent": a.email_sent or False,
        "response_status": a.response_status or "pending",
        "notes": a.notes or "",
        "cv_path": a.cv_path or "",
        "cover_letter_path": a.cover_letter_path or "",
        "email_subject": a.email_subject or "",
    }


@router.get("/", response_model=List[AppOut])
def list_applications(db: Session = Depends(get_db)):
    apps = db.query(Application).order_by(Application.created_at.desc()).all()
    return [_app_out(a, db) for a in apps]


@router.get("/{app_id:int}", response_model=AppOut)
def get_application(app_id: int, db: Session = Depends(get_db)):
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    return _app_out(a, db)


class StatusUpdate(BaseModel):
    response_status: str
    notes: Optional[str] = None


@router.patch("/{app_id:int}/status")
def update_response_status(app_id: int, body: StatusUpdate, db: Session = Depends(get_db)):
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    a.response_status = body.response_status
    if body.notes is not None:
        a.notes = body.notes
    # Sync job status
    j = db.query(Job).filter(Job.id == a.job_id).first()
    if j:
        j.status = body.response_status
    db.commit()
    return {"ok": True}


@router.delete("/{app_id:int}")
def delete_application(app_id: int, db: Session = Depends(get_db)):
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    db.delete(a)
    db.commit()
    return {"ok": True}
