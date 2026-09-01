"""
ATS-friendly PDF builder using ReportLab.
Generates both CV and Cover Letter as clean, single-column PDFs.
"""
from pathlib import Path
from typing import Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from config import settings

W, H = A4

# ── Colour palette (ATS safe = mostly black/grey) ────────────────────────────
ACCENT = colors.HexColor("#1a1a2e")
LIGHT = colors.HexColor("#444444")
RULE = colors.HexColor("#cccccc")

# ── Style helpers ─────────────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()
    s = {}
    s["name"] = ParagraphStyle("name", fontSize=18, fontName="Helvetica-Bold",
                                textColor=ACCENT, spaceAfter=2)
    s["subtitle"] = ParagraphStyle("subtitle", fontSize=10, fontName="Helvetica",
                                   textColor=LIGHT, spaceAfter=1)
    s["contact"] = ParagraphStyle("contact", fontSize=9, fontName="Helvetica",
                                  textColor=LIGHT, spaceAfter=6)
    s["section"] = ParagraphStyle("section", fontSize=11, fontName="Helvetica-Bold",
                                  textColor=ACCENT, spaceBefore=10, spaceAfter=2)
    s["body"] = ParagraphStyle("body", fontSize=9, fontName="Helvetica",
                               textColor=colors.black, leading=13, spaceAfter=2)
    s["bullet"] = ParagraphStyle("bullet", fontSize=9, fontName="Helvetica",
                                 textColor=colors.black, leading=13,
                                 leftIndent=12, bulletIndent=0, spaceAfter=1)
    s["bold"] = ParagraphStyle("bold", fontSize=9, fontName="Helvetica-Bold",
                               textColor=colors.black, spaceAfter=1)
    s["italic"] = ParagraphStyle("italic", fontSize=9, fontName="Helvetica-Oblique",
                                 textColor=LIGHT, spaceAfter=1)
    return s


def _rule():
    return HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=4)


def _section(title: str, s: dict):
    return [Paragraph(title.upper(), s["section"]), _rule()]


# ── CV PDF ─────────────────────────────────────────────────────────────────────

def build_cv_pdf(profile: Dict, cv_data: Dict, output_path: Path) -> Path:
    """Render an ATS-friendly CV PDF and return the path."""
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
    )
    s = _styles()
    story = []

    # ── Header ───────────────────────────────────────────────────────────────
    story.append(Paragraph(profile["name"], s["name"]))
    story.append(Paragraph(profile.get("title", "Software Engineer"), s["subtitle"]))
    contact_line = (
        f"{profile['email']}  |  {profile['phone']}  |  "
        f"{profile['portfolio']}  |  {profile['linkedin']}"
    )
    story.append(Paragraph(contact_line, s["contact"]))
    story.append(_rule())

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = cv_data.get("summary", "")
    if summary:
        story += _section("Professional Summary", s)
        story.append(Paragraph(summary, s["body"]))

    # ── Skills ────────────────────────────────────────────────────────────────
    story += _section("Technical Skills", s)
    skills = profile.get("skills", {})
    skill_rows = [
        ("Languages", ", ".join(skills.get("languages", []))),
        ("Frameworks", ", ".join(skills.get("frameworks", []))),
        ("Tools", ", ".join(skills.get("tools", []))),
        ("Databases", ", ".join(skills.get("databases", []))),
        ("Certifications", ", ".join(skills.get("certifications", []))),
    ]
    highlighted = cv_data.get("highlighted_skills", [])
    if highlighted:
        skill_rows.insert(0, ("Key Skills", ", ".join(highlighted)))
    for label, val in skill_rows:
        if val:
            story.append(Paragraph(f"<b>{label}:</b> {val}", s["body"]))

    # ── Experience ────────────────────────────────────────────────────────────
    story += _section("Experience", s)
    for exp in profile.get("experience", []):
        story.append(Paragraph(
            f"<b>{exp.get('role', '')}</b> — {exp.get('company', '')}  "
            f"<font color='#888888'>{exp.get('period', '')}</font>", s["body"]))
        achievements = cv_data.get("key_achievements") or exp.get("bullets", [])
        for b in achievements[:6]:
            story.append(Paragraph(f"• {b}", s["bullet"]))
        story.append(Spacer(1, 4))

    # ── Projects ──────────────────────────────────────────────────────────────
    story += _section("Projects", s)
    priority_names = cv_data.get("tailored_projects", [])
    projects = profile.get("projects", [])
    # Reorder: priority first
    ordered = sorted(projects, key=lambda p: (
        0 if p["name"] in priority_names else 1,
        priority_names.index(p["name"]) if p["name"] in priority_names else 99
    ))
    for proj in ordered[:5]:
        tech = ", ".join(proj.get("technologies", []))
        story.append(Paragraph(
            f"<b>{proj['name']}</b>  <font color='#888888'>[{tech}]</font>", s["body"]))
        story.append(Paragraph(proj.get("description", ""), s["bullet"]))
        for h in proj.get("highlights", [])[:2]:
            story.append(Paragraph(f"• {h}", s["bullet"]))
        story.append(Spacer(1, 3))

    # ── Education ─────────────────────────────────────────────────────────────
    story += _section("Education", s)
    for edu in profile.get("education", []):
        gpa = f" | GPA: {edu['gpa']}" if edu.get("gpa") else ""
        story.append(Paragraph(
            f"<b>{edu['degree']}</b> — {edu['institution']}", s["body"]))
        story.append(Paragraph(
            f"{edu['period']}{gpa}", s["italic"]))

    # ── Languages ─────────────────────────────────────────────────────────────
    story += _section("Languages", s)
    story.append(Paragraph(", ".join(profile.get("languages_spoken", [])), s["body"]))

    doc.build(story)
    return output_path


# ── Cover Letter PDF ──────────────────────────────────────────────────────────

def build_cover_letter_pdf(profile: Dict, job: Dict, text: str, output_path: Path) -> Path:
    """Render a professional cover letter PDF."""
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=2.5*cm, rightMargin=2.5*cm,
        topMargin=2.5*cm, bottomMargin=2.5*cm,
    )
    s = _styles()
    story = []

    story.append(Paragraph(profile["name"], s["name"]))
    story.append(Paragraph(
        f"{profile['email']}  |  {profile['phone']}  |  {profile['portfolio']}", s["contact"]))
    story.append(_rule())
    story.append(Spacer(1, 0.4*cm))

    # Company / role header
    story.append(Paragraph(f"Re: Application for <b>{job.get('title', 'Position')}</b>", s["bold"]))
    story.append(Paragraph(job.get("company", ""), s["italic"]))
    story.append(Spacer(1, 0.5*cm))

    # Body — split on newlines
    for para in text.strip().split("\n"):
        para = para.strip()
        if para:
            story.append(Paragraph(para, s["body"]))
            story.append(Spacer(1, 0.25*cm))

    doc.build(story)
    return output_path
