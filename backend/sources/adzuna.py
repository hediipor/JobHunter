"""Adzuna — keyword+location search across many countries (discovery, no company list)."""
import json
import logging
from typing import Dict, List, Tuple

import httpx

from config import settings
from sources.base import Source, SourceError, advance, combos, html_to_text, take
from sources.jsearch import _country_code

logger = logging.getLogger("sources.adzuna")

ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"


# Countries Adzuna has an endpoint for; anything else (ie, pt, tn, se…) would 404
SUPPORTED = {"gb", "us", "at", "au", "be", "br", "ca", "ch", "de", "es", "fr",
             "in", "it", "mx", "nl", "nz", "pl", "sg", "za"}


def _country(location: str) -> str | None:
    code = _country_code(location)
    return code if code in SUPPORTED else None


def _home_country(locations: List[str]) -> str | None:
    """Where "Remote" is searched: the country from the profile's location (set
    in setup), else the first supported location."""
    try:
        with open(settings.profile_path, encoding="utf-8") as f:
            code = _country(json.load(f).get("location") or "")
    except (OSError, ValueError):
        code = None
    return code or next((c for c in map(_country, locations) if c), None)


def _adzuna_to_dict(item: Dict, country: str) -> Dict:
    loc = item.get("location") or {}
    area = loc.get("area") or []
    # area[0] is the country in the LOCAL language ("España") and display_name
    # often omits it, so the country is the 2-letter code we queried with —
    # "Barcelona, ES" is what JSearch writes, so cross-source dedup merges them.
    city = area[-1] if area else (loc.get("display_name") or "").split(",")[0].strip()
    lo, hi = item.get("salary_min"), item.get("salary_max")
    salary = f"{lo:,.0f} - {hi:,.0f}" if lo and hi else f"{(lo or hi):,.0f}" if (lo or hi) else ""
    return {
        "title": item.get("title") or "",
        "company": (item.get("company") or {}).get("display_name") or "",
        "location": f"{city}, {country.upper()}" if city else country.upper(),
        # Adzuna truncates search descriptions to 500 chars and has no detail
        # API — don't add a per-job fetch, there is nothing to fetch.
        "description": html_to_text(item.get("description") or ""),
        "url": item.get("redirect_url") or "",
        "source": "adzuna",
        "job_type": (item.get("contract_time") or "").replace("_", "-"),
        "date_posted": (item.get("created") or "")[:10],
        "salary": salary,
    }


async def scrape_adzuna(client: httpx.AsyncClient, term: str, location: str, country: str) -> List[Dict]:
    """One search. Raises SourceError on auth/quota (every later query would fail too)."""
    remote = location.lower() == "remote"
    params = {
        "app_id": settings.adzuna_app_id, "app_key": settings.adzuna_app_key,
        "what": f"{term} remote" if remote else term,
        "results_per_page": 50, "max_days_old": 14,
    }
    # `where` wants a place inside the country; a country name matches nothing
    where = ", ".join(p.strip() for p in location.split(",") if p.strip() and not _country_code(p))
    if where and not remote:
        params["where"] = where
    r = await client.get(ADZUNA_URL.format(country=country), params=params)
    if r.status_code in (401, 403):
        raise SourceError("check ADZUNA_APP_ID / ADZUNA_APP_KEY")
    if r.status_code == 429:
        raise SourceError("429 — Adzuna quota exceeded")
    r.raise_for_status()
    return [_adzuna_to_dict(i, country) for i in r.json().get("results", [])]


class AdzunaSource(Source):
    name = "adzuna"

    def __init__(self, queries: int = 8):
        self.queries = queries

    async def fetch(self, terms: List[str], locations: List[str], budget: int) -> List[Dict]:
        if not (settings.adzuna_app_id and settings.adzuna_app_key):
            raise SourceError("ADZUNA_APP_ID / ADZUNA_APP_KEY not set")
        home = _home_country(locations)
        # (term, location, country); locations with no resolvable country are skipped
        pairs: List[Tuple[str, str, str]] = []
        for term, loc in combos(terms, locations):
            code = home if loc.lower() == "remote" else _country(loc)
            if code:
                pairs.append((term, loc, code))
        plan = take(self.name, pairs, self.queries)
        jobs: Dict[str, Dict] = {}
        used = failed = 0
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                for term, loc, code in plan:
                    try:
                        for job in await scrape_adzuna(client, term, loc, code):
                            if job["url"]:
                                jobs.setdefault(job["url"], job)
                    except SourceError:
                        raise
                    except Exception as exc:
                        failed += 1
                        logger.warning(f"[adzuna] {term} / {loc} → {exc}")
                    used += 1
                    if len(jobs) >= budget:
                        break
        finally:
            advance(self.name, used)
        if plan and failed == used:
            raise SourceError("every Adzuna search failed")
        return list(jobs.values())[:budget]
