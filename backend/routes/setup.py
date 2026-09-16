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
        "rapidapi_configured": bool(settings.rapidapi_key),
        "gmail_configured": bool(settings.gmail_from and settings.gmail_app_password),
        "profile_configured": profile_configured,
        "setup_complete": profile_configured,
    }


class KeysUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    rapidapi_key: Optional[str] = None
    gmail_from: Optional[str] = None
    gmail_app_password: Optional[str] = None


@router.post("/keys")
def update_keys(body: KeysUpdate):
    field_to_env = {
        "gemini_api_key": "GEMINI_API_KEY",
        "rapidapi_key": "RAPIDAPI_KEY",
        "gmail_from": "GMAIL_FROM",
        "gmail_app_password": "GMAIL_APP_PASSWORD",
    }
    provided = body.model_dump(exclude_none=True)
    updates = {field_to_env[k]: v for k, v in provided.items()}
    if updates:
        env_writer.write_env(BASE_DIR / ".env", updates)

    if "gemini_api_key" in provided:
        settings.gemini_api_key = provided["gemini_api_key"]
        from ai_generator import reload_client
        reload_client()
    if "rapidapi_key" in provided:
        settings.rapidapi_key = provided["rapidapi_key"]
    if "gmail_from" in provided:
        settings.gmail_from = provided["gmail_from"]
    if "gmail_app_password" in provided:
        settings.gmail_app_password = provided["gmail_app_password"]

    return {"ok": True}
