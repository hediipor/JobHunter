"""JSearch (RapidAPI) — aggregates LinkedIn, Indeed, Glassdoor, ZipRecruiter…"""
import asyncio
import logging
from typing import Dict, List

import httpx

from config import settings
from countries import COUNTRY_CODES as _COUNTRY_CODES
from sources.base import Source, SourceError, advance, combos, take

logger = logging.getLogger("sources.jsearch")

# v5 endpoint. NOTE: the `page` param is required in practice — without it the
# API returns 200 OK with an empty jobs array.
JSEARCH_URL = "https://jsearch.p.rapidapi.com/search-v2"

# Every scan costs one API request per query. The RapidAPI free tier allows
# ~200 requests/month — at 10/scan that's a 48h+ interval on the free plan.
MAX_JSEARCH_QUERIES_PER_SCAN = 10

# Seconds between sequential JSearch calls — rapid consecutive requests get
# soft-throttled (empty results instead of 429)
JSEARCH_DELAY_SECONDS = 3



def _country_code(location: str) -> str | None:
    """Country code for a location string. Handles 'City, Country' by taking the
    last comma-part, then any known country name appearing in the string."""
    parts = [p.strip().lower() for p in location.split(",")]
    for p in reversed(parts):
        if p in _COUNTRY_CODES:
            return _COUNTRY_CODES[p]
    loc = location.lower()
    return next((code for name, code in _COUNTRY_CODES.items() if name in loc), None)

_EMPLOYMENT_TYPES = {
    "FULLTIME": "full-time",
    "PARTTIME": "part-time",
    "CONTRACTOR": "contract",
    "INTERN": "internship",
}


def _jsearch_salary(item: Dict) -> str:
    # v5 provides a preformatted string when salary data exists
    if item.get("job_salary_string"):
        return str(item["job_salary_string"])
    lo, hi = item.get("job_min_salary"), item.get("job_max_salary")
    if not (lo or hi):
        return ""
    period = item.get("job_salary_period") or ""
    rng = f"{lo:,.0f} - {hi:,.0f}" if lo and hi else f"{(lo or hi):,.0f}"
    return f"{rng} ({period.lower()})" if period else rng


def _jsearch_job_type(item: Dict) -> str:
    # v5: job_employment_types is an enum list (['FULLTIME']),
    # job_employment_type is human-readable ("Full-time")
    types = item.get("job_employment_types")
    if isinstance(types, list) and types:
        mapped = _EMPLOYMENT_TYPES.get(str(types[0]))
        if mapped:
            return mapped
    return (item.get("job_employment_type") or "").lower()


def _jsearch_to_dict(item: Dict) -> Dict:
    if str(item.get("job_is_remote")).lower() == "true":
        location = "Remote"
    else:
        location = ", ".join(p for p in [item.get("job_city"), item.get("job_country")] if p)
    posted = item.get("job_posted_at_datetime_utc") or ""
    return {
        "title": item.get("job_title") or "",
        "company": item.get("employer_name") or "",
        "location": location,
        "description": item.get("job_description") or "",
        "url": item.get("job_apply_link") or "",
        "source": (item.get("job_publisher") or "jsearch").lower(),
        "job_type": _jsearch_job_type(item),
        "date_posted": posted[:10],
        "salary": _jsearch_salary(item),
    }


async def scrape_jsearch(client: httpx.AsyncClient, term: str, location: str) -> List[Dict]:
    """
    Query the JSearch API for one term/location combination. Raises
    SourceError on 403/429 — every later query would fail the same way.
    """
    params = {"query": term, "page": "1", "num_pages": "1", "date_posted": "week"}
    if location.lower() == "remote":
        params["query"] = f"{term} remote"
    else:
        params["query"] = f"{term} in {location}"
        code = _country_code(location)
        if code:
            params["country"] = code
    try:
        r = await client.get(
            JSEARCH_URL,
            params=params,
            headers={
                "X-RapidAPI-Key": settings.rapidapi_key,
                "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
            },
        )
        if r.status_code == 403:
            raise SourceError("403 — RAPIDAPI_KEY invalid or not subscribed to JSearch "
                              "(subscribe at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)")
        if r.status_code == 429:
            raise SourceError("429 — rate limit / monthly quota exceeded")
        r.raise_for_status()
        data = r.json().get("data")
        # v5 wraps results: {"jobs": [...], "cursor": ...}; older versions used a flat list
        items = data.get("jobs", []) if isinstance(data, dict) else (data or [])
    except SourceError:
        raise
    except Exception as exc:
        logger.warning(f"[jsearch] {params['query']} → {exc}")
        return []
    if not items:
        logger.info(f"[jsearch] no results for: {params['query']}")
    return [_jsearch_to_dict(item) for item in items]


class JSearchSource(Source):
    name = "jsearch"

    def __init__(self, queries: int = MAX_JSEARCH_QUERIES_PER_SCAN):
        self.queries = queries

    async def fetch(self, terms: List[str], locations: List[str], budget: int) -> List[Dict]:
        if not settings.rapidapi_key:
            raise SourceError("RAPIDAPI_KEY not set")
        plan = take(self.name, combos(terms, locations), self.queries)
        jobs: Dict[str, Dict] = {}
        used = 0
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                # Sequential with a pause: the JSearch free tier soft-throttles
                # rapid consecutive requests by returning empty results
                for i, (term, loc) in enumerate(plan):
                    if i:
                        await asyncio.sleep(JSEARCH_DELAY_SECONDS)
                    for job in await scrape_jsearch(client, term, loc):
                        if job["url"]:
                            jobs.setdefault(job["url"], job)
                    used += 1  # a 403/429 isn't "used": retry that pair next scan
                    if len(jobs) >= budget:
                        break
        finally:
            advance(self.name, used)
        return list(jobs.values())[:budget]
