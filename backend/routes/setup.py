"""
/setup endpoints — first-run configuration wizard (API keys + profile status).
"""
import json
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

import env_writer
from config import BASE_DIR, settings

router = APIRouter(prefix="/setup", tags=["setup"])


def _profile_configured() -> bool:
    try:
        with open(settings.profile_path, encoding="utf-8") as f:
            return bool(json.load(f).get("name"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False


@router.get("/status")
def get_status():
    profile_configured = _profile_configured()
    return {
        "gemini_configured": bool(settings.gemini_api_key),
        "groq_configured": bool(settings.groq_api_key),
        "rapidapi_configured": bool(settings.rapidapi_key),
        "gmail_configured": bool(settings.gmail_from and settings.gmail_app_password),
        "profile_configured": profile_configured,
        "setup_complete": profile_configured,
    }


class KeysUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    rapidapi_key: Optional[str] = None
    gmail_from: Optional[str] = None
    gmail_app_password: Optional[str] = None


@router.post("/keys")
def update_keys(body: KeysUpdate):
    provided = body.model_dump(exclude_none=True)
    if provided:
        env_writer.write_env(BASE_DIR / ".env", {k.upper(): v for k, v in provided.items()})
    # llm.py reads keys from settings on every call — no client to reload
    for k, v in provided.items():
        setattr(settings, k, v)

    return {"ok": True}
