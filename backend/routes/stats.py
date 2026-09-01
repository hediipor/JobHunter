"""
/stats endpoint — dashboard analytics
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Application, Job, get_db

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/")
def get_stats(db: Session = Depends(get_db)):
    total_jobs = db.query(func.count(Job.id)).scalar() or 0
    applied = db.query(func.count(Job.id)).filter(Job.is_applied == True).scalar() or 0
    interviews = db.query(func.count(Application.id)).filter(
        Application.response_status == "interview"
    ).scalar() or 0
    offers = db.query(func.count(Application.id)).filter(
        Application.response_status == "offer"
    ).scalar() or 0
    avg_score = db.query(func.avg(Job.match_score)).scalar() or 0

    # Jobs by source
    sources_raw = (
        db.query(Job.source, func.count(Job.id))
        .group_by(Job.source)
        .all()
    )
    sources = {s: c for s, c in sources_raw}

    # Score distribution buckets
    buckets = {"90-100": 0, "70-89": 0, "50-69": 0, "0-49": 0}
    for (score,) in db.query(Job.match_score).all():
        s = score or 0
        if s >= 90:
            buckets["90-100"] += 1
        elif s >= 70:
            buckets["70-89"] += 1
        elif s >= 50:
            buckets["50-69"] += 1
        else:
            buckets["0-49"] += 1

    # Recent jobs (top 5 by score)
    recent = (
        db.query(Job)
        .order_by(Job.match_score.desc())
        .limit(5)
        .all()
    )

    return {
        "total_jobs": total_jobs,
        "applied": applied,
        "interviews": interviews,
        "offers": offers,
        "avg_score": round(float(avg_score), 1),
        "sources": sources,
        "score_distribution": buckets,
        "top_jobs": [
            {"id": j.id, "title": j.title, "company": j.company, "score": j.match_score}
            for j in recent
        ],
    }
