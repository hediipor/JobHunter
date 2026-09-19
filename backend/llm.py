"""
The one door to every LLM call. All providers speak OpenAI-compatible
/chat/completions, so one httpx adapter covers them; a Provider is just data.

complete(prompt, tier=...) tries the tier's providers in order, spacing calls
per provider by its rpm, and keeps a daily budget in data/llm_budget.json so a
restart doesn't forget that today's quota is already spent.
"""
import asyncio
import datetime as dt
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Literal

import httpx

from config import BASE_DIR, settings

logger = logging.getLogger("llm")


@dataclass
class Provider:
    name: str
    base_url: str
    model: str
    api_key: str
    rpm: int
    rpd: int | None  # None = no daily cap worth tracking


class AllProvidersExhausted(Exception):
    """Every provider in the tier is out of quota (or unconfigured) — stop, don't retry."""


class LLMError(Exception):
    """A call failed for a non-quota reason (bad key, 5xx, network) on every provider."""


def _providers() -> dict[str, Provider]:
    # Built per call so a key saved from the setup wizard takes effect immediately.
    # Free-tier limits as of 2026-09, all three verified live 2026-09-19.
    return {p.name: p for p in (
        Provider("groq", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b",
                 settings.groq_api_key, rpm=30, rpd=1000),
        Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
                 "gemini-3.6-flash", settings.gemini_api_key, rpm=5, rpd=20),
        Provider("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-v4-flash-0731:free",
                 settings.openrouter_api_key, rpm=20, rpd=50),
    )}


TIERS = {
    "fast":    ["groq", "gemini", "openrouter"],   # triage — high volume
    "quality": ["gemini", "groq", "openrouter"],   # CV + cover letter — ~3/day
}


def configured() -> bool:
    return any(p.api_key for p in _providers().values())


# ── Persisted daily budget ───────────────────────────────────────────────────

BUDGET_PATH = BASE_DIR / "data" / "llm_budget.json"


def _load() -> dict:
    try:
        return json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save() -> None:
    tmp = BUDGET_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(_budget, indent=2), encoding="utf-8")
    os.replace(tmp, BUDGET_PATH)


_budget: dict = _load()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _entry(name: str) -> dict:
    """Today's budget row for a provider, reset on UTC date rollover."""
    today = _now().date().isoformat()
    e = _budget.get(name)
    if not e or e.get("date") != today:
        e = _budget[name] = {"date": today, "count": 0, "exhausted_until": None}
    return e


def _is_exhausted(p: Provider) -> bool:
    e = _entry(p.name)
    if e["exhausted_until"] and dt.datetime.fromisoformat(e["exhausted_until"]) > _now():
        return True
    return p.rpd is not None and e["count"] >= p.rpd


def _mark_exhausted(name: str) -> None:
    tomorrow = dt.datetime.combine(_now().date() + dt.timedelta(days=1), dt.time(), dt.timezone.utc)
    _entry(name)["exhausted_until"] = tomorrow.isoformat()
    _save()


def status() -> list[dict]:
    """Per-provider snapshot for GET /api/settings and the dashboard strip."""
    out = []
    for p in _providers().values():
        e = _entry(p.name)
        out.append({"name": p.name, "model": p.model, "configured": bool(p.api_key),
                    "used_today": e["count"], "daily_cap": p.rpd,
                    "exhausted": bool(p.api_key) and _is_exhausted(p)})
    return out


# ── Error classification ─────────────────────────────────────────────────────

def _duration(v: str) -> float:
    """Groq reset header: '2m59.56s', '7.66s', '120ms'."""
    mult = {"h": 3600, "m": 60, "s": 1, "ms": 0.001}
    return sum(float(n) * mult[u] for n, u in re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", v))


def _retry_after(body, headers=None) -> float:
    """Seconds to wait before retrying a per-minute 429 (+1s slack, capped at 65)."""
    headers = headers or {}
    if headers.get("retry-after"):
        try:
            return min(float(headers["retry-after"]) + 1, 65.0)
        except ValueError:
            pass
    resets = [_duration(v) for k, v in headers.items() if k.lower().startswith("x-ratelimit-reset")]
    if any(resets):
        return min(max(resets) + 1, 65.0)
    s = str(body)
    m = re.search(r"retry.?delay.*?seconds:\s*(\d+)", s, re.I | re.S) \
        or re.search(r'retryDelay"?\s*:\s*"(\d+(?:\.\d+)?)s', s) \
        or re.search(r"retry in (\d+(?:\.\d+)?)s", s, re.I)
    return min(float(m.group(1)) + 1, 65.0) if m else 20.0


def _is_daily(body: str) -> bool:
    # Gemini: quotaId "...PerDay...". Groq: "requests per day (RPD)" / "tokens per day (TPD)".
    return bool(re.search(r"PerDay|per day|\bRPD\b|\bTPD\b", body, re.I))


class _Daily(Exception):
    pass


# ── The door ─────────────────────────────────────────────────────────────────

_locks: dict[str, asyncio.Lock] = {}
_last_at: dict[str, float] = {}


async def _space(p: Provider) -> None:
    """Hold this provider's slot for 60/rpm s. Released before the request, so
    a slow response doesn't hold up the next call, and other providers never wait."""
    async with _locks.setdefault(p.name, asyncio.Lock()):
        wait = 60 / p.rpm - (time.monotonic() - _last_at.get(p.name, -1e9))
        if wait > 0:
            await asyncio.sleep(wait)
        _last_at[p.name] = time.monotonic()


async def _post(p: Provider, prompt: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=120) as client:
        return await client.post(
            f"{p.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {p.api_key}"},
            json={"model": p.model, "messages": [{"role": "user", "content": prompt}]},
        )


async def _call(p: Provider, prompt: str) -> str:
    """One provider, one retry on a per-minute 429. Raises _Daily on daily quota."""
    for attempt in (1, 2):
        await _space(p)
        r = await _post(p, prompt)
        if r.status_code == 429:
            if _is_daily(r.text):
                raise _Daily(r.text[:300])
            if attempt == 2:
                r.raise_for_status()
            wait = _retry_after(r.text, r.headers)
            logger.info(f"{p.name}: per-minute limit, retrying in {wait:.0f}s")
            await asyncio.sleep(wait)
            continue
        r.raise_for_status()
        _entry(p.name)["count"] += 1
        _save()
        return r.json()["choices"][0]["message"]["content"] or ""


async def complete(prompt: str, *, tier: Literal["fast", "quality"]) -> tuple[str, str]:
    """Try the tier's providers in order, skipping unconfigured and exhausted
    ones. Returns (text, provider_name).
    Raises AllProvidersExhausted if none has quota left, LLMError if the ones
    that did have quota all failed for other reasons."""
    providers = _providers()
    errors = []
    for name in TIERS[tier]:
        p = providers[name]
        if not p.api_key or _is_exhausted(p):
            continue
        try:
            return await _call(p, prompt), name
        except _Daily as exc:
            logger.warning(f"{name}: daily quota spent, skipping until UTC midnight — {exc}")
            _mark_exhausted(name)
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            logger.warning(f"{name}: {exc!r}, trying next provider")
            errors.append(f"{name}: {exc!r}")
    if errors:
        raise LLMError("; ".join(errors))
    raise AllProvidersExhausted(f"no {tier}-tier provider configured with quota left today")
