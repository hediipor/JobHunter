"""
Shared scan pipeline: scrape → skip known URLs → enrich Keejob details →
score → persist. Used by both the APScheduler job and the /jobs/scan route.
"""
import asyncio
import datetime
import json
import logging

from ai_generator import TriageQuotaExhausted, triage_job
from config import settings
from database import Job
from matcher import calculate_match
from scraper import enrich_keejob_details, scrape_all

logger = logging.getLogger("scan")

# In-memory scan status the frontend polls (GET /jobs/scan-status) so it can
# show "still running" / "done, N new jobs" instead of guessing with a timer —
# a scan (scrape + triage) can run for minutes, way past any fixed timeout.
# ponytail: single-process in-memory state — fine for one local user, would
# need a shared store (DB row, Redis) behind more than one uvicorn worker.
_scan_state: dict = {"running": False, "started_at": None, "finished_at": None, "added": None, "error": None}


def get_scan_state() -> dict:
    return dict(_scan_state)


# How many of each scan's new jobs get the Gemini triage pass — the highest
# keyword-scored ones. Calls are rate-limited (~13s apart) for the free tier,
# so this is also ≈ how many minutes triage adds to a scan.
TRIAGE_TOP_N = 10


def _load_profile() -> dict:
    with open(settings.profile_path, encoding="utf-8") as f:
        return json.load(f)


def _clean(s: str) -> str:
    """Drop lone surrogates (broken emoji from scraped HTML) that SQLite can't encode."""
    if not isinstance(s, str):
        return s
    return s.encode("utf-8", "ignore").decode("utf-8")


def _apply_triage(job: Job, result: dict) -> bool:
    """Write a triage_job() result onto a Job row (no commit). Returns False if
    the result was empty (API down / no key) so the row is left unassessed."""
    if result.get("fit_score") is None and not result.get("verdict"):
        return False
    job.ai_score = result.get("fit_score")
    job.ai_verdict = result.get("verdict", "")
    job.sponsorship = result.get("sponsorship", "") or "unclear"
    job.dealbreakers = json.dumps(result.get("dealbreakers", []))
    job.ai_assessed_at = datetime.datetime.utcnow()
    return True


async def triage_jobs(db, jobs: list[Job], profile: dict) -> None:
    """Run Gemini triage over the given Job rows, in place. Caller commits.
    Calls are serialised + rate-limited inside triage_job for the free tier."""
    if not (jobs and settings.gemini_api_key):
        return
    done = 0
    try:
        for job in jobs:
            if _apply_triage(job, await triage_job(profile, {
                "title": job.title, "company": job.company,
                "location": job.location, "description": job.description,
            })):
                done += 1
                db.commit()  # persist as we go — a mid-batch quota stop keeps progress
    except TriageQuotaExhausted:
        logger.warning(f"🤖 Triaged {done}/{len(jobs)} — Gemini daily free-tier quota spent, stopping")
        return
    logger.info(f"🤖 Triaged {done}/{len(jobs)} jobs")


async def scan_and_store(session_factory) -> list[int]:
    """Run a full scan, persist + triage new jobs. Returns the new job ids."""
    from user_settings import load as load_user_settings

    _scan_state.update(running=True, started_at=datetime.datetime.utcnow().isoformat(),
                        finished_at=None, added=None, error=None)
    try:
        ids = await _run_scan(session_factory)
        _scan_state.update(running=False, finished_at=datetime.datetime.utcnow().isoformat(), added=len(ids))
        return ids
    except Exception as exc:
        _scan_state.update(running=False, finished_at=datetime.datetime.utcnow().isoformat(), error=str(exc))
        raise


async def _run_scan(session_factory) -> list[int]:
    from user_settings import load as load_user_settings

    cfg = load_user_settings()
    jobs = await scrape_all(
        search_terms=cfg["search_terms"],
        locations=cfg["locations"],
        max_jobs=cfg["max_jobs_per_scan"],
    )
    profile = _load_profile()
    now = datetime.datetime.utcnow()
    db = session_factory()
    try:
        new_jobs = []
        for job_data in jobs:
            url = job_data.get("url", "")
            if not url:
                continue
            existing = db.query(Job).filter(Job.url == url).first()
            if existing:
                existing.last_seen = now  # still listed → keep it fresh
                continue
            new_jobs.append(job_data)

        # Only new jobs get the extra per-job detail fetch
        await enrich_keejob_details(new_jobs)

        rows = []
        for job_data in new_jobs:
            score, reasons = calculate_match(job_data, profile)
            row = Job(
                last_seen=now,
                title=_clean(job_data["title"]),
                company=_clean(job_data["company"]),
                location=_clean(job_data["location"]),
                description=_clean(job_data.get("description", "")),
                url=job_data["url"],
                source=_clean(job_data.get("source", "")),
                job_type=_clean(job_data.get("job_type", "")),
                date_posted=_clean(job_data.get("date_posted", "")),
                salary=_clean(job_data.get("salary", "")),
                match_score=score,
                match_reasons=json.dumps(reasons),
            )
            db.add(row)
            rows.append(row)
        db.commit()
        logger.info(f"✅ Scan done — {len(new_jobs)} new jobs added")

        # Gemini takes a closer look at the most promising new jobs
        rows.sort(key=lambda r: r.match_score or 0, reverse=True)
        await triage_jobs(db, rows[:TRIAGE_TOP_N], profile)
        db.commit()

        return [r.id for r in rows]
    finally:
        db.close()
