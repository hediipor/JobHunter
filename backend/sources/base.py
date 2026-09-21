"""
The job-source boundary. A source turns (terms, locations, budget) into job
dicts; the scan runner owns everything generic (dedup, scoring, triage).

Job dict keys: title, company, location, description, url, source,
job_type, date_posted, salary.
"""
import json
import logging
from itertools import zip_longest
from typing import Dict, List, Protocol, Sequence, Tuple, TypeVar

from config import BASE_DIR

logger = logging.getLogger("sources")

# Where each source's round-robin position survives restarts, so successive
# scans walk the whole terms × locations grid instead of restarting at the top.
CURSOR_PATH = BASE_DIR / "data" / "source_cursors.json"

T = TypeVar("T")
L = TypeVar("L")


class SourceError(Exception):
    """A source failed in a way worth telling the user about (bad key, quota)."""


class Source(Protocol):
    """Implementations subclass this (for the default enrich) and take
    `queries` — how many requests they may make per scan — in __init__."""
    name: str

    async def fetch(self, terms: List[str], locations: List[str], budget: int) -> List[Dict]:
        """At most `budget` jobs. Raise SourceError for user-facing failures."""

    async def enrich(self, jobs: List[Dict]) -> None:
        """Improve NEW jobs in place (e.g. fetch full descriptions). Default no-op."""
        return None


def combos(terms: Sequence[T], locations: Sequence[L]) -> List[Tuple[T, L]]:
    """Every (term, location) pair, ordered so any window of len(terms)
    consecutive pairs uses every term once, each at a different location
    (when there are at least as many locations as terms)."""
    return [(terms[i], locations[(i + r) % len(locations)])
            for r in range(len(locations)) for i in range(len(terms))]


def interleave(batches: Sequence[Sequence[Dict]]) -> List[Dict]:
    """Merge per-query results round-robin (1st of each, then 2nd of each, …),
    deduped by URL, so cutting the result to a budget keeps some of every query."""
    jobs: Dict[str, Dict] = {}
    for row in zip_longest(*batches):
        for job in row:
            if job is not None:
                jobs.setdefault(job["url"], job)
    return list(jobs.values())


def _load_cursors() -> Dict[str, int]:
    try:
        return json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def take(name: str, pairs: List[Tuple[T, L]], n: int) -> List[Tuple[T, L]]:
    """The next `n` pairs (wrapping) after where this source left off last scan."""
    if not pairs:
        return []
    start = _load_cursors().get(name, 0) % len(pairs)
    return [pairs[(start + k) % len(pairs)] for k in range(min(n, len(pairs)))]


def advance(name: str, used: int) -> None:
    """Move the cursor past the queries actually made (a source that stopped
    early resumes from where it stopped, not from where it planned to)."""
    if not used:
        return
    cursors = _load_cursors()
    cursors[name] = cursors.get(name, 0) + used
    try:
        CURSOR_PATH.write_text(json.dumps(cursors), encoding="utf-8")
    except OSError as exc:
        logger.warning(f"could not save source cursor: {exc}")
