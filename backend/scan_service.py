"""
Shared scan pipeline: scrape → skip known URLs → enrich Keejob details →
score → persist. Used by both the APScheduler job and the /jobs/scan route.
"""
import asyncio
import datetime
import json
import logging

import llm
from ai_generator import TRIAGE_VERSION, TriageParseError, triage_batch, triage_batches
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
_scan_state: dict = {"running": False, "started_at": None, "finished_at": None, "added": None, "error": None,
                     "triaged": None, "failed": None, "skipped": None, "triage_error": None}


def get_scan_state() -> dict:
    return dict(_scan_state)


def _load_profile() -> dict:
    with open(settings.profile_path, encoding="utf-8") as f:
        return json.load(f)


def _clean(s: str) -> str:
    """Drop lone surrogates (broken emoji from scraped HTML) that SQLite can't encode."""
    if not isinstance(s, str):
        return s
    return s.encode("utf-8", "ignore").decode("utf-8")


def _apply_triage(job: Job, result: dict, provider: str, model: str) -> None:
    """Write one parsed assessment onto a Job row (no commit)."""
    job.ai_score = result["fit_score"]
    job.ai_verdict = result["verdict"]
    job.sponsorship = result["sponsorship"] or "unclear"
    job.dealbreakers = json.dumps(result["dealbreakers"])
    job.ai_assessed_at = datetime.datetime.utcnow()
    job.ai_provider, job.ai_model, job.triage_version = provider, model, TRIAGE_VERSION


def _job_dict(job: Job) -> dict:
    return {"id": job.id, "title": job.title, "company": job.company,
            "location": job.location, "description": job.description}


async def triage_jobs(db, jobs: list[Job], profile: dict) -> dict:
    """AI-triage the given Job rows in place, in the order given (highest
    priority first), committing after each call. Returns
    {triaged, failed, skipped, error}: skipped = never tried because every
    provider's quota ran out; error = the last failure, for the dashboard."""
    stats = {"triaged": 0, "failed": 0, "skipped": 0, "error": None}
    if not jobs:
        return stats
    if not llm.configured():
        stats.update(skipped=len(jobs), error="no LLM API key configured")
        return stats

    rows = {j.id: j for j in jobs}

    async def run(batch: list[dict]) -> None:
        results, provider, model = await triage_batch(profile, batch)
        for d, r in zip(batch, results):
            _apply_triage(rows[d["id"]], r, provider, model)
        stats["triaged"] += len(batch)
        db.commit()  # persist as we go — a mid-scan quota stop keeps progress

    async def attempt(batch: list[dict]) -> None:
        """A batch that fails or comes back malformed/misaligned is retried
        one job per call, so one bad answer can't cost (or mislabel) the rest."""
        try:
            return await run(batch)
        except (TriageParseError, llm.LLMError) as exc:
            if len(batch) == 1:
                logger.warning(f"triage failed for job {batch[0]['id']}: {exc}")
                stats["failed"] += 1
                stats["error"] = str(exc)
                return
            logger.warning(f"batch of {len(batch)} failed ({exc}), retrying one by one")
        for one in batch:
            await attempt([one])

    try:
        for batch in triage_batches(profile, [_job_dict(j) for j in jobs]):
            await attempt(batch)
    except llm.AllProvidersExhausted as exc:
        stats["skipped"] = len(jobs) - stats["triaged"] - stats["failed"]
        stats["error"] = str(exc)
        logger.warning(f"🤖 every LLM provider's daily quota is spent — {stats['skipped']} job(s) left pending")
    logger.info(f"🤖 Triage: {stats['triaged']} assessed, {stats['failed']} failed, {stats['skipped']} skipped")
    return stats


async def scan_and_store(session_factory) -> list[int]:
    """Run a full scan, persist + triage new jobs. Returns the new job ids."""
    from user_settings import load as load_user_settings

    _scan_state.update(running=True, started_at=datetime.datetime.utcnow().isoformat(),
                        finished_at=None, added=None, error=None,
                        triaged=None, failed=None, skipped=None, triage_error=None)
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
    # Sync SQLAlchemy on the event loop — deliberate: local SQLite, sub-ms queries.
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

        # Every new job gets the AI check. The keyword score only decides the
        # order, so if the day's quota runs out it's the weakest that stay pending.
        rows.sort(key=lambda r: r.match_score or 0, reverse=True)
        t = await triage_jobs(db, rows, profile)
        _scan_state.update(triaged=t["triaged"], failed=t["failed"], skipped=t["skipped"],
                           triage_error=t["error"])
        db.commit()

        return [r.id for r in rows]
    finally:
        db.close()
