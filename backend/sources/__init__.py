"""
Job sources. Add one by writing a Source (see base.py) and registering it here;
user_settings picks up its defaults and the Settings page shows its toggle.
"""
import asyncio
import logging
from typing import Dict, List, Tuple

from sources.base import Source
from sources.jsearch import JSearchSource
from sources.keejob import KeejobSource

logger = logging.getLogger("sources")

REGISTRY: Dict[str, type] = {
    JSearchSource.name: JSearchSource,
    KeejobSource.name: KeejobSource,
}


def enabled_sources(cfg: Dict) -> List[Source]:
    """One instance per enabled source, each with its own query budget."""
    return [REGISTRY[name](queries=c["queries"])
            for name, c in cfg["sources"].items() if name in REGISTRY and c["enabled"]]


def budget_for(i: int, n: int, total: int) -> int:
    """Source i's share of `total` new jobs; the shares sum to exactly `total`."""
    share, extra = divmod(total, n)
    return share + (i < extra)


async def fetch_all(sources: List[Source], terms: List[str], locations: List[str],
                    total: int) -> List[Tuple[Source, List[Dict] | BaseException]]:
    """Every source fetches concurrently within its own share of `total`.
    A source that raises comes back as its exception; the others are unaffected."""
    results = await asyncio.gather(
        *(s.fetch(terms, locations, budget_for(i, len(sources), total)) for i, s in enumerate(sources)),
        return_exceptions=True,
    )
    out = []
    for i, (s, r) in enumerate(zip(sources, results)):
        if isinstance(r, BaseException):
            logger.warning(f"[{s.name}] failed: {r}")
        else:
            # Enforced here too, so a buggy source can't eat another's share
            r = r[:budget_for(i, len(sources), total)]
            logger.info(f"[{s.name}] {len(r)} jobs")
        out.append((s, r))
    return out
