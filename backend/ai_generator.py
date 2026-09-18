"""
AI document generator. Produces: tailored CV data, cover letter text, and
application email. Every model call goes through llm.complete().
"""
import json
import logging
import re
from typing import Dict, Tuple

import llm

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


_TRIAGE_FALLBACK = {"fit_score": None, "verdict": "", "sponsorship": "", "dealbreakers": []}


async def triage_job(profile: Dict, job: Dict) -> Dict:
    """
    One fast-tier LLM call that screens a posting for THIS candidate. Returns
    {fit_score: int|None, verdict: str, sponsorship: str, dealbreakers: [str]}.
    Raises llm.AllProvidersExhausted so a batch can stop instead of spinning.
    """

    prompt = f"""You are screening a job posting for a specific candidate. Be strict and realistic.

CANDIDATE:
{_candidate_summary(profile)}

JOB:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Description (excerpt):
{(job.get('description') or '')[:3500]}

Return:
1. fit_score (0-100): realistic fit for this candidate's actual level and stack. A senior/lead
   role for an early-career candidate scores low even with a matching stack.
2. verdict: ONE plain sentence — the single thing that matters most about this fit.
3. sponsorship: one of
   - "yes"     — posting explicitly offers visa sponsorship / relocation, OR role is remote and hires globally,
                 OR the candidate is already located in the job's country
   - "likely"  — not stated, but a large international employer where sponsorship for this role is common
   - "unclear" — not mentioned and cannot be inferred
   - "no"      — posting requires existing work authorization / citizenship / security clearance,
                 or says sponsorship is not available
4. dealbreakers: array of SHORT strings — hard blockers for THIS candidate only
   (e.g. "Requires 5+ years experience", "Requires EU citizenship", "On-site only, no relocation",
   "Requires native German"). Empty array if none.

Respond with ONLY a valid JSON object — no markdown:
{{"fit_score": 0, "verdict": "", "sponsorship": "unclear", "dealbreakers": []}}"""

    try:
        raw, _ = await llm.complete(prompt, tier="fast")
        data = json.loads(_clean_json(raw))
        fs = data.get("fit_score")
        return {
            "fit_score": float(fs) if isinstance(fs, (int, float)) else None,
            "verdict": str(data.get("verdict", "")).strip(),
            "sponsorship": str(data.get("sponsorship", "unclear")).strip().lower(),
            "dealbreakers": [str(d).strip() for d in data.get("dealbreakers", []) if str(d).strip()],
        }
    except llm.AllProvidersExhausted:
        raise
    except Exception as exc:
        logger.warning(f"triage failed for {job.get('title', '?')}: {exc}")
        return dict(_TRIAGE_FALLBACK)


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
- Write 3-5 achievement bullets from the experience section, emphasising what matches the JD.

Respond with ONLY a valid JSON object — no markdown, no extra text:
{{
  "summary": "...",
  "highlighted_skills": ["...", "..."],
  "tailored_projects": ["Project Name 1", "Project Name 2"],
  "key_achievements": ["...", "..."]
}}"""

    raw, _ = await llm.complete(prompt, tier="quality")
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

    text, _ = await llm.complete(prompt, tier="quality")
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
