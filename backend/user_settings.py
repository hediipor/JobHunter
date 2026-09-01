"""
User-adjustable app settings, persisted to data/settings.json.
Defaults come from .env / scraper constants; edits from the Settings UI
override them and survive restarts.
"""
import json
import logging
from typing import Any, Dict

from config import BASE_DIR, settings
from scraper import DEFAULT_LOCATIONS, DEFAULT_SEARCH_TERMS

logger = logging.getLogger("user_settings")

SETTINGS_PATH = BASE_DIR / "data" / "settings.json"

DEFAULTS: Dict[str, Any] = {
    "scan_interval_hours": settings.scan_interval_hours,
    "max_jobs_per_scan": settings.max_jobs_per_scan,
    "search_terms": DEFAULT_SEARCH_TERMS,
    "locations": DEFAULT_LOCATIONS,
}


def load() -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"settings.json unreadable, using defaults: {exc}")
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def save(cfg: Dict[str, Any]) -> None:
    keep = {k: cfg[k] for k in DEFAULTS if k in cfg}
    SETTINGS_PATH.write_text(
        json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8"
    )
