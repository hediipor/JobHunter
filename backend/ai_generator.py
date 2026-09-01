"""
AI document generator using Google Gemini.
Produces: tailored CV data, cover letter text, and application email.
"""
import asyncio
import json
import re
from typing import Dict, List, Tuple

import google.generativeai as genai

from config import settings

genai.configure(api_key=settings.gemini_api_key)
_model = genai.GenerativeModel("gemini-2.5-flash")


def _clean_json(raw: str) -> str:
    """Strip markdown fences from a Gemini JSON response."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _call(prompt: str) -> str:
    response = _model.generate_content(prompt)
    return response.text


# ── CV tailoring ─────────────────────────────────────────────────────────────

async def generate_cv_data(profile: Dict, job: Dict) -> Dict:
    """
    Ask Gemini to tailor the CV data for the specific job.
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

    raw = await asyncio.to_thread(_call, prompt)
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

    return await asyncio.to_thread(_call, prompt)


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
