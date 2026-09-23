"""
AI document generator. Produces: tailored CV data, cover letter text, and
application email. Every model call goes through llm.complete().
"""
import json
import logging
import re
from typing import Dict, Tuple

import llm
import preferences

logger = logging.getLogger("ai_generator")


def _clean_json(raw: str) -> str:
    """Strip markdown fences from a model's JSON response."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


# ── Job triage (fit + visa sponsorship + dealbreakers) ───────────────────────

def _candidate_summary(profile: Dict) -> str:
    exp = profile.get("experience", [])
    yrs = "~1 year (internship only)" if len(exp) <= 1 else f"{len(exp)} past roles"
    sk = profile.get("skills", {})
    stack = ", ".join(sk.get("languages", []) + sk.get("frameworks", []))
    return (
        f"{profile.get('title', 'Software Engineer')}, {yrs} of professional experience, "
        f"based in {profile.get('location', 'unknown')}. "
        f"For on-site roles outside the home country the candidate needs visa sponsorship "
        f"and relocation; globally-remote roles are fine.\n"
        f"Actively targeting: {', '.join(profile.get('target_locations', []))} — these are "
        f"deliberate, not a mismatch; don't lower fit_score just for being outside the home "
        f"country if it's one of these. Still flag real posting requirements as dealbreakers "
        f"(e.g. 'EU citizenship required', 'must already hold a work permit').\n"
        f"Education: {'; '.join(e.get('degree', '') for e in profile.get('education', [])[:2])}.\n"
        f"Stack: {stack}.\n"
        f"Spoken languages: {', '.join(profile.get('languages_spoken', []))}.\n"
        f"Target roles: {', '.join(profile.get('target_roles', [])[:6])}."
    )


# Bump when the triage prompt changes: rows with an older version can then be
# re-triaged selectively. NULL = assessed before versioning existed.
TRIAGE_VERSION = 2

# Job text per posting in the prompt — same for batches and singles, so
# batching doesn't change what the model sees.
DESC_CHARS = 3000

# Estimated prompt tokens per batch call. Groq's free gpt-oss-120b allows 8K
# tokens/min *per request included*, and hidden reasoning + output
# (llm.COMPLETION_ALLOWANCE) come on top — ~4K prompt keeps a call well under.
BATCH_PROMPT_TOKENS = 4000


class TriageParseError(Exception):
    """The response wasn't one valid assessment per requested job id."""


def _job_block(job: Dict) -> str:
    return (f"--- JOB id={job['id']} ---\n"
            f"Title: {job.get('title', '')}\n"
            f"Company: {job.get('company', '')}\n"
            f"Location: {job.get('location', '')}\n"
            f"Description (excerpt):\n{(job.get('description') or '')[:DESC_CHARS]}\n")


def _triage_prompt(profile: Dict, jobs: list[Dict]) -> str:
    note = preferences.get_note()
    note_block = (
        f"\nWHAT THIS CANDIDATE HAS SAID ABOUT SIMILAR JOBS (from their own 👍/👎):\n{note}\n"
        if note else ""
    )
    return f"""You are screening job postings for a specific candidate. Be strict and realistic.
Assess each job independently.

CANDIDATE:
{_candidate_summary(profile)}
{note_block}
JOBS:
{"".join(_job_block(j) for j in jobs)}
For each job return:
- id: the job's id exactly as given above
- fit_score (0-100): realistic fit for this candidate's actual level and stack. A senior/lead
  role for an early-career candidate scores low even with a matching stack.
- verdict: ONE plain sentence — the single thing that matters most about this fit.
- sponsorship: one of
   "yes"     — posting explicitly offers visa sponsorship / relocation, OR role is remote and hires globally,
               OR the candidate is already located in the job's country
   "likely"  — not stated, but a large international employer where sponsorship for this role is common
   "unclear" — not mentioned and cannot be inferred
   "no"      — posting requires existing work authorization / citizenship / security clearance,
               or says sponsorship is not available
- dealbreakers: array of SHORT strings — hard blockers for THIS candidate only
   (e.g. "Requires 5+ years experience", "Requires EU citizenship", "On-site only, no relocation",
   "Requires native German"). Empty array if none.

Respond with ONLY a valid JSON array, one object per job ({len(jobs)} total) — no markdown:
[{{"id": 0, "fit_score": 0, "verdict": "", "sponsorship": "unclear", "dealbreakers": []}}]"""


def _parse_assessment(d) -> Dict:
    if not isinstance(d, dict):
        raise TriageParseError(f"not an object: {d!r:.80}")
    fs = d.get("fit_score")
    if isinstance(fs, bool) or not isinstance(fs, (int, float)) or not 0 <= fs <= 100:
        raise TriageParseError(f"bad fit_score {fs!r}")
    verdict = str(d.get("verdict") or "").strip()
    if not verdict:
        raise TriageParseError("empty verdict")
    sponsorship = str(d.get("sponsorship") or "").strip().lower()
    deals = d.get("dealbreakers") or []
    if not isinstance(deals, list):
        raise TriageParseError("dealbreakers not a list")
    return {
        "fit_score": float(fs),
        "verdict": verdict,
        "sponsorship": sponsorship if sponsorship in ("yes", "likely", "unclear", "no") else "unclear",
        "dealbreakers": [str(x).strip() for x in deals if str(x).strip()],
    }


def parse_triage(raw: str, ids: list[int]) -> list[Dict]:
    """Assessments aligned to `ids`, matched by id — not by position. Raises
    TriageParseError unless there is exactly one valid assessment per id:
    a wrong verdict on the wrong job is worse than no verdict."""
    try:
        data = json.loads(_clean_json(raw))
    except ValueError as exc:
        raise TriageParseError(f"not JSON: {exc}")
    if isinstance(data, dict) and len(ids) == 1:
        data = [data]  # some models unwrap a one-element array
    if not isinstance(data, list) or len(data) != len(ids):
        raise TriageParseError(f"expected {len(ids)} assessments, got "
                               f"{len(data) if isinstance(data, list) else type(data).__name__}")
    by_id = {}
    for d in data:
        try:
            jid = int(d.get("id")) if isinstance(d, dict) else None
        except (TypeError, ValueError):
            jid = None
        if jid not in ids or jid in by_id:
            raise TriageParseError(f"unexpected or duplicate id {d.get('id') if isinstance(d, dict) else d!r:.40}")
        by_id[jid] = _parse_assessment(d)
    return [by_id[i] for i in ids]


def triage_batches(profile: Dict, jobs: list[Dict]) -> list[list[Dict]]:
    """Group jobs (in the given priority order) into batches that fit
    BATCH_PROMPT_TOKENS, estimated at ~4 chars/token."""
    overhead = len(_triage_prompt(profile, [])) // 4
    batches, cur, used = [], [], overhead
    for j in jobs:
        t = len(_job_block(j)) // 4
        if cur and used + t > BATCH_PROMPT_TOKENS:
            batches.append(cur)
            cur, used = [], overhead
        cur.append(j)
        used += t
    return batches + ([cur] if cur else [])


async def triage_batch(profile: Dict, jobs: list[Dict]) -> tuple[list[Dict], str, str]:
    """
    One fast-tier LLM call that screens several postings (each dict needs an
    `id`) for THIS candidate. Returns (assessments aligned to jobs, provider,
    model); each assessment is {fit_score, verdict, sponsorship, dealbreakers}.
    Raises TriageParseError on a malformed/misaligned response, and lets
    llm.AllProvidersExhausted / llm.LLMError through for the caller to count.
    """
    raw, provider, model = await llm.complete(_triage_prompt(profile, jobs), tier="fast")
    return parse_triage(raw, [j["id"] for j in jobs]), provider, model


# ── CV tailoring ─────────────────────────────────────────────────────────────

async def generate_cv_data(profile: Dict, job: Dict) -> Dict:
    """
    Ask the quality-tier LLM to tailor the CV data for the specific job.
    Returns a dict with keys: summary, highlighted_skills, tailored_projects, key_achievements.
    """
    prompt = f"""You are a professional resume writer. Tailor this candidate's CV for the given job posting.

CANDIDATE PROFILE (JSON):
{json.dumps(profile, indent=2, ensure_ascii=False)}

JOB POSTING:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Description:
{(job.get('description') or '')[:3000]}

INSTRUCTIONS:
- Do NOT invent any new skills, jobs, or experiences — use only what is in the profile.
- Write a 2-3 sentence professional summary tailored to this role.
- Select and reorder the most relevant skills (max 12).
- Select and reorder the most relevant projects (max 4).
- Write 3-5 achievement bullets from the most recent role in the experience section only, emphasising what matches the JD.

Respond with ONLY a valid JSON object — no markdown, no extra text:
{{
  "summary": "...",
  "highlighted_skills": ["...", "..."],
  "tailored_projects": ["Project Name 1", "Project Name 2"],
  "key_achievements": ["...", "..."]
}}"""

    raw, *_ = await llm.complete(prompt, tier="quality")
    try:
        return json.loads(_clean_json(raw))
    except Exception:
        return {
            "summary": f"Motivated software engineer seeking {job.get('title', 'this role')} at {job.get('company', 'your company')}.",
            "highlighted_skills": profile.get("skills", {}).get("frameworks", [])[:8],
            "tailored_projects": [p["name"] for p in profile.get("projects", [])[:4]],
            "key_achievements": [b for b in profile.get("experience", [{}])[0].get("bullets", [])[:4]],
        }


# ── Cover letter ──────────────────────────────────────────────────────────────

async def generate_cover_letter(profile: Dict, job: Dict, cv_data: Dict) -> str:
    """Generate a professional cover letter (plain text, ~300 words)."""
    skills_str = ", ".join(cv_data.get("highlighted_skills", [])[:8])
    prompt = f"""Write a professional, enthusiastic cover letter for this job application.

CANDIDATE: {profile['name']}
EMAIL: {profile['email']} | PHONE: {profile['phone']}
PORTFOLIO: {profile['portfolio']}
KEY SKILLS: {skills_str}
PROFESSIONAL SUMMARY: {cv_data.get('summary', '')}

JOB: {job.get('title', '')} at {job.get('company', '')} ({job.get('location', '')})
JOB DESCRIPTION (excerpt):
{(job.get('description') or '')[:2000]}

INSTRUCTIONS:
- 3 paragraphs: why this role, what I bring, call to action.
- Mention the company name specifically.
- Reference 2-3 concrete skills or projects from the profile.
- Professional yet warm tone. Max 300 words.
- Start directly with "Dear Hiring Manager," — no extra headers.
- End with: Sincerely,\\n{profile['name']}"""

    text, *_ = await llm.complete(prompt, tier="quality")
    return text


# ── Application email ─────────────────────────────────────────────────────────

def _cover_letter_hook(cover_letter: str) -> str:
    """
    First body paragraph of the cover letter, minus salutation and sign-off,
    so the email can reuse it without duplicating "Dear ..." greetings.
    """
    paras = [p.strip() for p in cover_letter.strip().split("\n\n") if p.strip()]
    for p in paras:
        low = p.lower()
        if low.startswith(("sincerely", "best regards", "kind regards")):
            break
        if low.startswith("dear"):
            # Salutation glued to the first paragraph with a single newline
            parts = p.split("\n", 1)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip()
            continue
        return p
    return ""


async def generate_email(profile: Dict, job: Dict, cover_letter: str) -> Tuple[str, str]:
    """
    Return (subject, body) for the application email.
    The body is a short note reusing the cover letter's opening paragraph;
    the full cover letter and CV are sent as PDF attachments.
    """
    subject = f"Application for {job.get('title', 'Position')} — {profile['name']}"

    hook = _cover_letter_hook(cover_letter)
    hook_block = f"\n\n{hook}" if hook else ""

    body = f"""Dear Hiring Team at {job.get('company', 'your company')},

Please find attached my CV and cover letter for the {job.get('title', 'position')} role.{hook_block}

I would welcome the opportunity to discuss how my skills can contribute to {job.get('company', 'your team')}.

Best regards,
{profile['name']}
{profile['email']} | {profile['phone']}
{profile['portfolio']}
{profile['linkedin']}
"""
    return subject, body
