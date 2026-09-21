"""
/stats endpoint — dashboard analytics
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Application, Job, fresh_jobs, get_db

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/")
def get_stats(db: Session = Depends(get_db)):
    # Dashboard reflects the current (fresh) board; applied/interviews/offers
    # stay global since they track history.
    fresh = fresh_jobs(db).subquery()
    total_jobs = db.query(func.count(fresh.c.id)).scalar() or 0
    applied = db.query(func.count(Job.id)).filter(Job.is_applied == True).scalar() or 0
    interviews = db.query(func.count(Application.id)).filter(
        Application.response_status == "interview"
    ).scalar() or 0
    offers = db.query(func.count(Application.id)).filter(
        Application.response_status == "offer"
    ).scalar() or 0
    # Scores are the AI fit score only (Job.fit_score), and only assessed jobs
    # count — a pending job has no score, not a score of 0.
    scored = fresh_jobs(db).filter(Job.fit_score.isnot(None))
    assessed = scored.count()
    avg_score = scored.with_entities(func.avg(Job.fit_score)).scalar() or 0

    # Jobs by source
    sources_raw = (
        db.query(fresh.c.source, func.count(fresh.c.id))
        .group_by(fresh.c.source)
        .all()
    )
    sources = {s: c for s, c in sources_raw}

    # Fit score distribution buckets
    buckets = {"90-100": 0, "70-89": 0, "50-69": 0, "0-49": 0}
    for (s,) in scored.with_entities(Job.fit_score).all():
        if s >= 90:
            buckets["90-100"] += 1
        elif s >= 70:
            buckets["70-89"] += 1
        elif s >= 50:
            buckets["50-69"] += 1
        else:
            buckets["0-49"] += 1

    top = scored.order_by(Job.fit_score.desc()).limit(5).all()

    return {
        "total_jobs": total_jobs,
        "assessed": assessed,
        "applied": applied,
        "interviews": interviews,
        "offers": offers,
        "avg_score": round(float(avg_score), 1),
        "sources": sources,
        "score_distribution": buckets,
        "top_jobs": [
            {"id": j.id, "title": j.title, "company": j.company, "score": j.fit_score}
            for j in top
        ],
    }


@router.post("/digest")
def send_digest_now(db: Session = Depends(get_db)):
    """Email the daily digest on demand — covers jobs added in the last 26h."""
    from digest import send_daily_digest

    since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=26)
    ids = [i for (i,) in db.query(Job.id).filter(Job.created_at >= since).all()]
    if not send_daily_digest(db, ids):
        raise HTTPException(400, "Nothing to send (no recent jobs, or Gmail/digest disabled).")
    return {"message": f"Digest sent — {len(ids)} recent job(s)."}
