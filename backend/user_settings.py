"""
User-adjustable app settings, persisted to data/settings.json.
Defaults come from .env / the constants below / each source; edits from the Settings UI
override them and survive restarts.
"""
import json
import logging
from typing import Any, Dict

from config import BASE_DIR, settings
from sources import REGISTRY

logger = logging.getLogger("user_settings")

SETTINGS_PATH = BASE_DIR / "data" / "settings.json"

# ── Search terms derived from profile target roles ──────────────────────────
DEFAULT_SEARCH_TERMS = [
    "Software Engineer",
    "Full Stack Developer",
    "Web Developer",
    "Flutter Developer",
    "React Developer",
    "Angular Developer",
    "Python Developer",
    "Software Engineering Intern",
    "Web Development Intern",
]

DEFAULT_LOCATIONS = [
    "Barcelona, Spain",
    "Spain",
    "Canada",
    "Netherlands",
    "Germany",
    "Ireland",
    "Remote",
    "France",
    "Portugal",
    "United Kingdom",
]

DEFAULTS: Dict[str, Any] = {
    "scan_interval_hours": settings.scan_interval_hours,
    "max_jobs_per_scan": settings.max_jobs_per_scan,
    "search_terms": DEFAULT_SEARCH_TERMS,
    "locations": DEFAULT_LOCATIONS,
    # per source: on/off + requests it may make per scan (its own API quota).
    # The max_jobs_per_scan budget is split between the enabled ones.
    "sources": {name: {"enabled": True, "queries": cls().queries} for name, cls in REGISTRY.items()},
}


def load() -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"settings.json unreadable, using defaults: {exc}")
    cfg = {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
    # merge per source, so a newly registered source shows up with its defaults
    saved = data.get("sources") or {}
    cfg["sources"] = {n: {**d, **saved.get(n, {})} for n, d in DEFAULTS["sources"].items()}
    return cfg


def save(cfg: Dict[str, Any]) -> None:
    keep = {k: cfg[k] for k in DEFAULTS if k in cfg}
    SETTINGS_PATH.write_text(
        json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8"
    )
