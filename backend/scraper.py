"""
Job scraper — pulls from LinkedIn, Indeed, Glassdoor and more via the
JSearch API (RapidAPI), plus Keejob.com (custom BeautifulSoup scraper).
"""
import asyncio
import logging
from typing import Dict, List

import httpx
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger("scraper")


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


# ── JSearch (RapidAPI) — aggregates LinkedIn, Indeed, Glassdoor, ZipRecruiter… ─

# v5 endpoint. NOTE: the `page` param is required in practice — without it the
# API returns 200 OK with an empty jobs array.
JSEARCH_URL = "https://jsearch.p.rapidapi.com/search-v2"

# Every scan costs one API request per query. The RapidAPI free tier allows
# ~200 requests/month — at 10/scan that's a 48h+ interval on the free plan.
MAX_JSEARCH_QUERIES_PER_SCAN = 10

# Seconds between sequential JSearch calls — rapid consecutive requests get
# soft-throttled (empty results instead of 429)
JSEARCH_DELAY_SECONDS = 3

# ISO country codes for the JSearch `country` param
_COUNTRY_CODES = {
    "tunisia": "tn",
    "france": "fr",
    "germany": "de",
    "united kingdom": "gb",
    "uk": "gb",
    "canada": "ca",
    "united states": "us",
    "usa": "us",
    "spain": "es",
    "netherlands": "nl",
    "ireland": "ie",
    "portugal": "pt",
    "belgium": "be",
    "switzerland": "ch",
    "italy": "it",
    "austria": "at",
    "sweden": "se",
    "poland": "pl",
}


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


async def scrape_jsearch(client: httpx.AsyncClient, term: str, location: str) -> List[Dict] | None:
    """
    Query the JSearch API for one term/location combination.
    Returns None on a 403 (key invalid / not subscribed) so the caller can
    abort the whole batch instead of burning through queries that can't succeed.
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
            logger.warning("[jsearch] 403 — RAPIDAPI_KEY invalid or not subscribed to JSearch "
                           "(subscribe at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)")
            return None
        if r.status_code == 429:
            logger.warning("[jsearch] 429 — rate limit / monthly quota exceeded")
            return []
        r.raise_for_status()
        data = r.json().get("data")
        # v5 wraps results: {"jobs": [...], "cursor": ...}; older versions used a flat list
        items = data.get("jobs", []) if isinstance(data, dict) else (data or [])
    except Exception as exc:
        logger.warning(f"[jsearch] {params['query']} → {exc}")
        return []
    if not items:
        logger.info(f"[jsearch] no results for: {params['query']}")
    return [_jsearch_to_dict(item) for item in items]


# Keejob is French-language — English terms like "Software Engineer" miss most
# listings, so it gets its own search vocabulary
KEEJOB_TERMS = [
    "developpeur",
    "full stack",
    "ingenieur informatique",
    "web",
    "mobile",
    "stage informatique",
]


def _keejob_icon_text(card, icon_class: str) -> str:
    """Text of the span next to a FontAwesome icon (Keejob's metadata pattern)."""
    icon = card.select_one(f"i.{icon_class}")
    if not icon:
        return ""
    span = icon.find_next("span")
    return " ".join(span.get_text(strip=True).split()) if span else ""


async def scrape_keejob(term: str) -> List[Dict]:
    """Scrape keejob.com for Tunisian listings (Tailwind layout, <article> cards)."""
    jobs: List[Dict] = []
    url = f"https://www.keejob.com/offres-emploi/?keywords={term.replace(' ', '+')}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "lxml")
        for card in soup.find_all("article")[:10]:
            title_link = card.select_one("h2 a[href*='/offres-emploi/']")
            if not title_link:
                continue
            href = title_link["href"]
            title = title_link.get_text(strip=True)

            company_el = card.select_one("h2 + p")
            company = company_el.get_text(strip=True) if company_el else ""

            location = _keejob_icon_text(card, "fa-map-marker-alt") or "Tunisia"
            date_posted = _keejob_icon_text(card, "fa-clock")

            salary_icon = card.select_one("i.fa-money-bill-wave")
            salary = salary_icon.parent.get_text(strip=True) if salary_icon else ""

            contract_tags = [i.parent.get_text(strip=True) for i in card.select("i.fa-briefcase")]
            if "stage" in title.lower():
                job_type = "internship"
            elif contract_tags == ["CDI"] or contract_tags == ["CDD"]:
                job_type = "full-time"
            else:
                job_type = ""  # cards often list every contract type at once

            desc_el = card.select_one("div.mb-3 p")
            description = desc_el.get_text(" ", strip=True) if desc_el else ""

            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "description": description,
                "url": href if href.startswith("http") else f"https://www.keejob.com{href}",
                "source": "keejob",
                "job_type": job_type,
                "date_posted": date_posted,
                "salary": salary,
            })
    except Exception as exc:
        logger.warning(f"[keejob] {term} → {exc}")
    return jobs


def _parse_keejob_detail(html: str) -> str:
    """
    Full description from a Keejob detail page: the "Description de l'annonce"
    block plus the "Détails de l'annonce" metadata (contract type, required
    experience, languages) — the latter helps experience-level matching.
    """
    soup = BeautifulSoup(html, "lxml")
    parts = []
    for label in ("Description de l", "Détails de l"):
        h2 = soup.find(lambda t: t.name == "h2" and label in t.get_text())
        if h2:
            block = h2.find_next("div")
            if block:
                text = " ".join(block.get_text(" ", strip=True).split())
                if text:
                    parts.append(text)
    return "\n\n".join(parts)


async def enrich_keejob_details(jobs: List[Dict], concurrency: int = 5) -> None:
    """
    Replace Keejob snippet descriptions with the full text from each job's
    detail page. Mutates the dicts in place. Call this on NEW jobs only —
    every job costs one page fetch.
    """
    targets = [j for j in jobs if j.get("source") == "keejob" and j.get("url")]
    if not targets:
        return
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(
        timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}
    ) as client:
        async def fetch(job: Dict):
            async with sem:
                try:
                    r = await client.get(job["url"])
                    desc = _parse_keejob_detail(r.text)
                    if desc:
                        job["description"] = desc
                except Exception as exc:
                    logger.warning(f"[keejob detail] {job['url']} → {exc}")
        await asyncio.gather(*(fetch(j) for j in targets))
    logger.info(f"[keejob] enriched {len(targets)} job descriptions")


async def scrape_all(
    search_terms: List[str] | None = None,
    locations: List[str] | None = None,
    max_jobs: int | None = None,
) -> List[Dict]:
    """Master scraper — JSearch (sequential, rate-limited) + Keejob (concurrent)."""
    terms = search_terms or DEFAULT_SEARCH_TERMS
    locs = locations or DEFAULT_LOCATIONS
    limit = max_jobs or settings.max_jobs_per_scan

    # Alternate the top 2 terms across locations (Software Engineer, Full Stack
    # Developer, Software Engineer, ...) rather than exhausting term[0] across
    # every location before term[1] ever fires. With more locations than the
    # query budget, term[0]-first starved term[1] out of the scan entirely —
    # half the keyword variety, fewer unique postings, lower average score
    # (jobs that only a second term's wording would catch never got pulled).
    terms2 = terms[:2] or terms[:1]
    combos = [(terms2[i % len(terms2)], l) for i, l in enumerate(locs)][:MAX_JSEARCH_QUERIES_PER_SCAN]

    all_jobs: List[Dict] = []
    seen_urls: set = set()

    def _add(batch: List[Dict]):
        for job in batch:
            url = job.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_jobs.append(job)

    # Tunisian boards — concurrent, independent of JSearch quota.
    # Uses its own French terms; the English defaults miss most Keejob listings.
    keejob_task = asyncio.gather(
        *(scrape_keejob(term) for term in KEEJOB_TERMS), return_exceptions=True
    )

    if settings.rapidapi_key:
        async with httpx.AsyncClient(timeout=90) as client:
            # Sequential with a pause: the JSearch free tier soft-throttles
            # rapid consecutive requests by returning empty results
            for i, (term, loc) in enumerate(combos):
                if i > 0:
                    await asyncio.sleep(JSEARCH_DELAY_SECONDS)
                batch = await scrape_jsearch(client, term, loc)
                if batch is None:  # 403 — key unusable, no point continuing
                    break
                _add(batch)
                if len(all_jobs) >= limit:
                    break
    else:
        logger.warning("[jsearch] RAPIDAPI_KEY not set — skipping JSearch")

    for batch in await keejob_task:
        if isinstance(batch, list):
            _add(batch)

    logger.info(f"[scrape_all] {len(all_jobs)} unique jobs collected")
    return all_jobs[:limit]
