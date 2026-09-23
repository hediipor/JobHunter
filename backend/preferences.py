"""
Preferences note: a short LLM-written summary of what the candidate has said
via 👍/👎 on jobs, injected into the triage prompt so future scans get
sharper. Cached in data/preferences.json; regenerated only after enough new
ratings have come in — not on every scan.
"""
import datetime
import json
import logging
import os

import llm
from config import BASE_DIR
from database import Job

logger = logging.getLogger("preferences")

PATH = BASE_DIR / "data" / "preferences.json"
MAX_CHARS = 600            # hard cap — the triage batch budget is tight
REGEN_THRESHOLD = 5        # new ratings needed before spending an LLM call again
CAP_PER_SIDE = 15          # most recent 👍 / 👎 sent to the LLM


def _load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, PATH)


def get_note() -> str:
    """The cached note (sync, no LLM call) — what ai_generator injects into
    the triage prompt. Empty string if none has been generated yet."""
    return _load().get("note") or ""


def _rated_lines(db) -> list[str]:
    """Most recent CAP_PER_SIDE 👍 and 👎, one line each: title/company/
    location/AI verdict/reason — what the LLM sees to write the note."""
    def lines(feedback: int) -> list[str]:
        rows = (
            db.query(Job)
            .filter(Job.feedback == feedback)
            .order_by(Job.ai_assessed_at.desc(), Job.id.desc())
            .limit(CAP_PER_SIDE)
            .all()
        )
        tag = "LIKED" if feedback == 1 else "DISLIKED"
        out = []
        for j in rows:
            reason = f" — reason: {j.feedback_reason}" if j.feedback_reason else ""
            out.append(f"{tag}: {j.title} at {j.company} ({j.location}). "
                       f"AI verdict was: {j.ai_verdict or 'n/a'}{reason}")
        return out

    return lines(1) + lines(-1)


async def build_note(db) -> str:
    """One fast-tier LLM call turning the candidate's rated jobs into a short
    screening note. Empty string if nothing is rated yet. Truncated hard at
    MAX_CHARS regardless of what the model returns."""
    lines = _rated_lines(db)
    if not lines:
        return ""
    prompt = (
        "A candidate rated these job postings a recruiting AI showed them, thumbs up or "
        "down, sometimes with a short reason. Write a SHORT note (max 100 words) as "
        "guidance for a job screener: what this candidate wants, and what to avoid. Be "
        "specific and concrete about seniority, stack, location or company patterns you "
        "see. Plain text, no markdown, no preamble.\n\n" + "\n".join(lines)
    )
    text, *_ = await llm.complete(prompt, tier="fast")
    return text.strip()[:MAX_CHARS]


async def refresh(db) -> str:
    """Regenerate and cache the note if the rated count grew by >= REGEN_THRESHOLD
    since it was last generated; otherwise return the cached note unchanged.
    Never raises: an LLM failure logs a warning and keeps the previous note, so
    a scan calling this can't be broken by it."""
    cached = _load()
    rated_count = db.query(Job).filter(Job.feedback.isnot(None)).count()
    if rated_count - cached.get("rated_count", 0) < REGEN_THRESHOLD:
        return cached.get("note", "")
    try:
        note = await build_note(db)
    except (llm.LLMError, llm.AllProvidersExhausted) as exc:
        logger.warning(f"preferences note regeneration failed, keeping previous note: {exc}")
        return cached.get("note", "")
    _save({"note": note, "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
           "rated_count": rated_count})
    return note
