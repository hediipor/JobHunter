"""
Shared scan pipeline: scrape → skip known URLs → enrich Keejob details →
score → persist. Used by both the APScheduler job and the /jobs/scan route.
"""
import json
import logging

from config import settings
from database import Job
from matcher import calculate_match
from scraper import enrich_keejob_details, scrape_all

logger = logging.getLogger("scan")


def _load_profile() -> dict:
    with open(settings.profile_path, encoding="utf-8") as f:
        return json.load(f)


async def scan_and_store(session_factory) -> int:
    """Run a full scan and persist new jobs. Returns the number added."""
    from user_settings import load as load_user_settings

    cfg = load_user_settings()
    jobs = await scrape_all(
        search_terms=cfg["search_terms"],
        locations=cfg["locations"],
        max_jobs=cfg["max_jobs_per_scan"],
    )
    profile = _load_profile()
    db = session_factory()
    try:
        new_jobs = []
        for job_data in jobs:
            url = job_data.get("url", "")
            if not url:
                continue
            if db.query(Job).filter(Job.url == url).first():
                continue
            new_jobs.append(job_data)

        # Only new jobs get the extra per-job detail fetch
        await enrich_keejob_details(new_jobs)

        for job_data in new_jobs:
            score, reasons = calculate_match(job_data, profile)
            db.add(Job(
                title=job_data["title"],
                company=job_data["company"],
                location=job_data["location"],
                description=job_data.get("description", ""),
                url=job_data["url"],
                source=job_data.get("source", ""),
                job_type=job_data.get("job_type", ""),
                date_posted=job_data.get("date_posted", ""),
                salary=job_data.get("salary", ""),
                match_score=score,
                match_reasons=json.dumps(reasons),
            ))
        db.commit()
        logger.info(f"✅ Scan done — {len(new_jobs)} new jobs added")
        return len(new_jobs)
    finally:
        db.close()
