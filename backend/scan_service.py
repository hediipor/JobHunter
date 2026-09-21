"""
Shared scan pipeline: fetch from every enabled source → skip known URLs →
let each source enrich its new jobs → score → persist → triage. Used by both the APScheduler job and the /jobs/scan route.
"""
import asyncio
import datetime
import json
import logging

from sqlalchemy import and_, or_

import llm
from ai_generator import TRIAGE_VERSION, TriageParseError, triage_batch, triage_batches
from config import settings
from database import Job, content_key
from matcher import calculate_match
from sources import enabled_sources, fetch_all

logger = logging.getLogger("scan")

# In-memory scan status the frontend polls (GET /jobs/scan-status) so it can
# show "still running" / "done, N new jobs" instead of guessing with a timer —
# a scan (scrape + triage) can run for minutes, way past any fixed timeout.
# ponytail: single-process in-memory state — fine for one local user, would
# need a shared store (DB row, Redis) behind more than one uvicorn worker.
_scan_state: dict = {"running": False, "started_at": None, "finished_at": None, "added": None, "error": None,
                     "triaged": None, "failed": None, "skipped": None, "triage_error": None,
                     "source_errors": {}}


def get_scan_state() -> dict:
    return dict(_scan_state)


# Same idea for "Run AI Check" (routes/jobs.py): the result of the last run.
_triage_state: dict = {"running": False, "finished_at": None, "triaged": None,
                       "failed": None, "skipped": None, "error": None}


def get_triage_state() -> dict:
    return dict(_triage_state)


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
    job.ai_assessed_at = datetime.datetime.now(datetime.UTC)
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


def _add_seen(pairs: list, source: str, url: str) -> None:
    if [source, url] not in pairs:
        pairs.append([source, url])


def dedup(db, source_name: str, jobs: list[dict], pending: dict, now) -> list[dict]:
    """Return the jobs never seen before, stamped with content_key/also_seen.
    A repeat — same url, or same content_key from a DIFFERENT source (one board
    listing two urls means two postings), whether stored or earlier in this
    scan (`pending`, shared across sources) — is recorded on the first sighting
    instead: stored rows get last_seen bumped, and a different (source, url)
    pair is appended to also_seen. No company → url matching only."""
    fresh = []
    for jd in jobs:
        url = jd.get("url", "")
        if not url:
            continue
        src = jd.get("source") or source_name
        company = jd.get("company", "")
        key = content_key(jd.get("title", ""), company, jd.get("location", ""))
        by_key = bool(company.strip())
        first = pending.get(url)
        if first is None and by_key:
            first = next((j for j in pending.get(("key", key), []) if j["source"] != src), None)
        if first is not None:
            if [src, url] != [first["source"], first["url"]]:
                _add_seen(first["also_seen"], src, url)
            continue
        match = Job.url == url
        if by_key:
            match = or_(match, and_(Job.content_key == key, Job.source.is_distinct_from(src)))
        row = db.query(Job).filter(match).first()
        if row:
            row.last_seen = now  # still listed → keep it fresh
            if [src, url] != [row.source, row.url]:
                pairs = json.loads(row.also_seen or "[]")
                _add_seen(pairs, src, url)
                row.also_seen = json.dumps(pairs)
            continue
        jd.update(source=src, content_key=key, also_seen=[])
        pending[url] = jd
        pending.setdefault(("key", key), []).append(jd)
        fresh.append(jd)
    return fresh


async def scan_and_store(session_factory) -> list[int] | None:
    """Run a full scan, persist + triage new jobs. Returns the new job ids, or
    None if a scan is already running (nothing was done)."""
    # The guard and the flag flip happen before the first await, so on the one
    # event loop two callers (schedule + manual) can't both get past it — two
    # scans racing to insert the same new URL would hit the unique constraint.
    if _scan_state["running"]:
        return None
    _scan_state.update(running=True, started_at=datetime.datetime.now(datetime.UTC).isoformat(),
                        finished_at=None, added=None, error=None,
                        triaged=None, failed=None, skipped=None, triage_error=None,
                        source_errors={})
    try:
        ids = await _run_scan(session_factory)
        _scan_state.update(running=False, finished_at=datetime.datetime.now(datetime.UTC).isoformat(), added=len(ids))
        return ids
    except Exception as exc:
        _scan_state.update(running=False, finished_at=datetime.datetime.now(datetime.UTC).isoformat(), error=str(exc))
        raise


async def _run_scan(session_factory) -> list[int]:
    from user_settings import load as load_user_settings

    cfg = load_user_settings()
    sources = enabled_sources(cfg)
    if not sources:
        raise RuntimeError("every job source is disabled in Settings")
    results = await fetch_all(sources, cfg["search_terms"], cfg["locations"], cfg["max_jobs_per_scan"])
    # "JSearch failed: 403 — …" for the dashboard, instead of just fewer jobs
    _scan_state["source_errors"] = {s.name: str(r) or type(r).__name__
                                    for s, r in results if isinstance(r, BaseException)}
    profile = _load_profile()
    now = datetime.datetime.now(datetime.UTC)
    # Sync SQLAlchemy on the event loop — deliberate: local SQLite, sub-ms queries.
    db = session_factory()
    try:
        new_jobs, pending = [], {}
        for source, jobs in results:
            if isinstance(jobs, BaseException):
                continue
            fresh = dedup(db, source.name, jobs, pending, now)
            # Only new jobs get the source's extra per-job fetch. A failed
            # enrich still keeps the jobs, with their snippet descriptions.
            try:
                await source.enrich(fresh)
            except Exception as exc:
                logger.warning(f"[{source.name}] enrich failed: {exc}")
                _scan_state["source_errors"][source.name] = f"enrich: {exc}"
            new_jobs += fresh

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
                content_key=job_data["content_key"],
                also_seen=json.dumps(job_data["also_seen"]),
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
