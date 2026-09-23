"""
/settings endpoints — read and update user-adjustable app settings.
API keys stay in .env; only their presence is reported here.
"""
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import llm
import user_settings
from config import settings

logger = logging.getLogger("settings_routes")

router = APIRouter(prefix="/settings", tags=["settings"])


class SourceSettings(BaseModel):
    enabled: bool
    queries: int = Field(ge=1, le=50)


class SettingsUpdate(BaseModel):
    scan_interval_hours: int = Field(ge=1, le=168)
    max_jobs_per_scan: int = Field(ge=1, le=200)
    search_terms: List[str]
    locations: List[str]
    sources: Dict[str, SourceSettings]


@router.get("/")
def get_settings() -> Dict[str, Any]:
    cfg = user_settings.load()
    cfg["keys"] = {
        "gemini": bool(settings.gemini_api_key),
        "groq": bool(settings.groq_api_key),
        "openrouter": bool(settings.openrouter_api_key),
        "gmail": bool(settings.gmail_app_password),
        "rapidapi": bool(settings.rapidapi_key),
    }
    cfg["gmail_from"] = settings.gmail_from
    cfg["llm_providers"] = llm.status()
    return cfg


@router.put("/")
def update_settings(body: SettingsUpdate):
    cfg = body.model_dump()
    cfg["search_terms"] = [t.strip() for t in cfg["search_terms"] if t.strip()]
    cfg["locations"] = [l.strip() for l in cfg["locations"] if l.strip()]
    if not cfg["search_terms"] or not cfg["locations"]:
        raise HTTPException(422, "Need at least one search term and one location")
    user_settings.save(cfg)

    # Apply the new interval to the running scheduler
    try:
        from scheduler import reschedule_scan
        reschedule_scan(cfg["scan_interval_hours"])
    except Exception as exc:
        logger.warning(f"Could not reschedule scan job: {exc}")

    return {"ok": True}
