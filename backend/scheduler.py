"""
Background scheduler — scans for new jobs every N hours using APScheduler.
"""
import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from database import SessionLocal
from digest import send_daily_digest
from scan_service import scan_and_store
from user_settings import load as load_user_settings

logger = logging.getLogger("scheduler")
scheduler = BackgroundScheduler(timezone="UTC")
_loop: asyncio.AbstractEventLoop | None = None  # the app's loop, set at startup


def run_scan():
    """Synchronous wrapper called by APScheduler: scan, then email the digest."""
    logger.info("⏰ Scheduled scan started")
    try:
        # hand the scan to the app loop; this thread just waits for it
        new_ids = asyncio.run_coroutine_threadsafe(scan_and_store(SessionLocal), _loop).result()
    except Exception as exc:
        logger.error(f"❌ Scan failed: {exc}")
        return

    db = SessionLocal()
    try:
        # blocking SMTP is fine here: we're on the scheduler thread, not the loop
        send_daily_digest(db, new_ids)
    except Exception as exc:
        logger.error(f"❌ Digest failed: {exc}")
    finally:
        db.close()


def start_scheduler(loop: asyncio.AbstractEventLoop):
    global _loop
    _loop = loop
    hours = load_user_settings()["scan_interval_hours"]
    scheduler.add_job(
        run_scan,
        trigger="interval",
        hours=hours,
        id="job_scan",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"🕐 Scheduler started — scans every {hours}h")


def reschedule_scan(hours: int):
    """Apply a new scan interval without restarting the app."""
    scheduler.reschedule_job("job_scan", trigger="interval", hours=hours)
    logger.info(f"🕐 Scan interval updated — every {hours}h")


def stop_scheduler():
    scheduler.shutdown(wait=False)
