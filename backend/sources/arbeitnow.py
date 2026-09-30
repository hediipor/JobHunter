"""Arbeitnow — free, keyless job board feed (mostly DE/EU, many visa-friendly)."""
import logging
from datetime import datetime, timezone
from typing import Dict, List

import httpx

from sources.base import Source, SourceError, html_to_text, rank_by_terms

logger = logging.getLogger("sources.arbeitnow")

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"


# The feed's job_types is mostly seniority ("entry", "berufserfahren"); keep only real employment types
EMPLOYMENT_TYPES = {"full-time", "part-time", "contract", "internship", "temporary", "freelance"}


def _arbeitnow_to_dict(item: Dict) -> Dict:
    created = item.get("created_at")
    types = item.get("job_types") or []
    return {
        "title": item.get("title") or "",
        "company": item.get("company_name") or "",
        # City only, no country: dedup won't merge these with other sources
        # (a missed merge, never a wrong one). Don't invent a country.
        "location": "Remote" if item.get("remote") else item.get("location") or "",
        "description": html_to_text(item.get("description") or ""),
        "url": item.get("url") or "",
        "source": "arbeitnow",
        "job_type": next((t for t in (str(t).lower().replace("_", "-") for t in types)
                          if t in EMPLOYMENT_TYPES), ""),
        "date_posted": datetime.fromtimestamp(created, timezone.utc).strftime("%Y-%m-%d") if created else "",
        "salary": "",
    }


class ArbeitnowSource(Source):
    """No search parameter: fetch the newest pages, keep what matches the terms."""
    name = "arbeitnow"

    def __init__(self, queries: int = 2):
        self.queries = queries  # pages per scan

    async def fetch(self, terms: List[str], locations: List[str], budget: int) -> List[Dict]:
        items: List[Dict] = []
        url, errors = ARBEITNOW_URL, []
        async with httpx.AsyncClient(timeout=30) as client:
            for _ in range(self.queries):
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    body = r.json()
                except Exception as exc:
                    logger.warning(f"[arbeitnow] {url} → {exc}")
                    errors.append(exc)
                    break
                items += body.get("data", [])
                url = (body.get("links") or {}).get("next")
                if not url:
                    break
        if errors and not items:
            raise SourceError(f"Arbeitnow request failed: {errors[-1]}")
        ranked = rank_by_terms(items, terms, lambda i: f"{i.get('title', '')} {' '.join(i.get('tags') or [])}")
        jobs = (_arbeitnow_to_dict(i) for i in ranked)
        return [j for j in jobs if j["url"]][:budget]
