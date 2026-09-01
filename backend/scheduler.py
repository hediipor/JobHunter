"""
Background scheduler — scans for new jobs every N hours using APScheduler.
"""
import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from database import SessionLocal
from scan_service import scan_and_store
from user_settings import load as load_user_settings

logger = logging.getLogger("scheduler")
scheduler = BackgroundScheduler(timezone="UTC")


def run_scan():
    """Synchronous wrapper called by APScheduler."""
    logger.info("⏰ Scheduled scan started")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(scan_and_store(SessionLocal))
    except Exception as exc:
        logger.error(f"❌ Scan failed: {exc}")
    finally:
        loop.close()


def start_scheduler():
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
