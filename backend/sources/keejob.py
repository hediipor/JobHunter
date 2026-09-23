"""Keejob.com — Tunisian listings, scraped (Tailwind layout, <article> cards)."""
import asyncio
import logging
from typing import Dict, List

import httpx
from bs4 import BeautifulSoup

from sources.base import Source, SourceError, advance, combos, interleave, take

logger = logging.getLogger("sources.keejob")


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
    """Scrape keejob.com for Tunisian listings (Tailwind layout, <article> cards).
    Raises on any failure, including a page with no parseable cards: these
    terms always have listings, so zero cards means the HTML changed."""
    jobs: List[Dict] = []
    url = f"https://www.keejob.com/offres-emploi/?keywords={term.replace(' ', '+')}"
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
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
    if not jobs:
        raise ValueError("no job cards parsed (layout changed?)")
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


class KeejobSource(Source):
    """Ignores the user's English terms and locations: Keejob is French-language
    and Tunisia-only, so it walks its own vocabulary."""
    name = "keejob"

    def __init__(self, queries: int = len(KEEJOB_TERMS)):
        self.queries = queries

    async def fetch(self, terms: List[str], locations: List[str], budget: int) -> List[Dict]:
        plan = take(self.name, combos(KEEJOB_TERMS, [None]), self.queries)
        results = await asyncio.gather(*(scrape_keejob(term) for term, _ in plan),
                                       return_exceptions=True)
        advance(self.name, len(plan))
        batches = []
        for (term, _), r in zip(plan, results):
            if isinstance(r, Exception):
                logger.warning(f"[keejob] {term} → {r}")
            else:
                batches.append(r)
        if plan and not batches:
            raise SourceError(f"every Keejob search failed (last: {results[-1]})")
        return interleave(batches)[:budget]

    async def enrich(self, jobs: List[Dict], concurrency: int = 5) -> None:
        """
        Replace snippet descriptions with the full text from each job's detail
        page. Mutates the dicts in place. NEW jobs only — each costs a fetch.
        """
        targets = [j for j in jobs if j.get("url")]
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
