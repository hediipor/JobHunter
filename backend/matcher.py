"""
Match scoring — rates a job posting against a candidate profile (0-100).
Returns (score, reasons_list).
"""
import json
import re
from typing import Dict, List, Tuple

def profile_skills(profile: Dict | None) -> List[str]:
    """Every skill in profile["skills"] (lists of strings), lowercased, deduped."""
    lists = ((profile or {}).get("skills") or {}).values()
    return list(dict.fromkeys(str(x).strip().lower() for l in lists if isinstance(l, list) for x in l if str(x).strip()))


JUNIOR_KEYWORDS = [
    "junior", "entry", "graduate", "fresh", "intern", "stage",
    "trainee", "0-2 year", "1 year", "2 years", "débutant", "graduate",
]

SENIOR_KEYWORDS = [
    "senior", "lead", "principal", "staff", "10 years", "8 years", "expert",
]

RELEVANT_TITLES = [
    "software", "developer", "engineer", "fullstack", "full stack",
    "frontend", "backend", "mobile", "web", "flutter", "react",
    "angular", "python", "node", "intern", "stage",
]


def calculate_match(job: Dict, profile: Dict | None = None) -> Tuple[float, List[str]]:
    """
    Score a job dict against the candidate profile.
    Returns (score 0-100, list of human-readable reason strings).
    """
    description = ((job.get("description") or "") + " " + (job.get("title") or "")).lower()
    title = (job.get("title") or "").lower()
    reasons: List[str] = []
    score = 0.0

    # ── 1. Skills match (up to 50 pts) ──────────────────────────────────────
    # lookarounds instead of \b so skills ending in a symbol ("c++") still match
    matched = [s for s in profile_skills(profile)
               if re.search(rf"(?<!\w){re.escape(s)}(?!\w)", description)]
    skill_score = min(50.0, len(matched) * 4.0)
    score += skill_score
    if matched:
        display = [s.title() for s in matched[:6]]
        reasons.append(f"Matching skills: {', '.join(display)}")

    # ── 2. Title relevance (up to 20 pts) ───────────────────────────────────
    title_hits = [kw for kw in RELEVANT_TITLES if kw in title]
    title_score = min(20.0, len(title_hits) * 5.0)
    score += title_score
    if title_hits:
        reasons.append(f"Relevant title keywords: {', '.join(title_hits[:4])}")

    # ── 3. Experience level match (up to 20 pts) ────────────────────────────
    is_junior = any(kw in description for kw in JUNIOR_KEYWORDS)
    is_senior = any(kw in description for kw in SENIOR_KEYWORDS)
    if is_junior and not is_senior:
        score += 20.0
        reasons.append("Junior / entry-level position — perfect experience match")
    elif is_senior and not is_junior:
        score = max(0.0, score - 10.0)
        reasons.append("Senior role — may require more experience")
    else:
        score += 10.0
        reasons.append("Mid-level position")

    # ── 4. Language bonus (up to 10 pts) ────────────────────────────────────
    spoken = ["english", "french", "arabic", "german"]
    lang_hits = [l for l in spoken if l in description]
    if lang_hits:
        score += min(10.0, len(lang_hits) * 3.0)
        reasons.append(f"Language match: {', '.join(l.title() for l in lang_hits)}")

    score = round(max(0.0, min(100.0, score)), 1)
    return score, reasons
