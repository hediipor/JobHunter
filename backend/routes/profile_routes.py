"""
/profile endpoint — read and update user profile JSON
"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict

from config import settings

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/")
def get_profile() -> Dict[str, Any]:
    try:
        with open(settings.profile_path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(404, "Profile not found")


@router.put("/")
def update_profile(data: Dict[str, Any]):
    with open(settings.profile_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"ok": True}
