"""
Daily digest email — a summary of the jobs a scan just added, ranked by the
AI fit score (Job.fit_score); jobs not yet assessed are listed as pending.
Sent after each scheduled scan by scheduler.run_scan.
"""
import html
import json
import logging

from config import settings
from database import Job
from email_sender import send_digest

logger = logging.getLogger("digest")

# Fit score at/above which a job goes in the "strong matches" block.
STRONG_CUTOFF = 65
# Hard cap on rows so the email stays skimmable.
MAX_ROWS = 12

_SPONSOR_LABEL = {
    "yes": "✅ sponsors / remote-ok",
    "likely": "🟡 sponsorship likely",
    "unclear": "❔ sponsorship unclear",
    "no": "⛔ no sponsorship",
}


def job_url(job_id: int) -> str:
    """Link to a job's detail page — the static export serves /jobs/detail/?id=."""
    return f"{settings.frontend_url}/jobs/detail/?id={job_id}"


def _rank(j: Job) -> tuple:
    """Assessed jobs by fit, highest first; pending ones after."""
    return (j.fit_score is not None, j.fit_score or 0)


def _deals(j: Job) -> list[str]:
    try:
        return json.loads(j.dealbreakers or "[]")
    except Exception:
        return []


def _row(j: Job) -> str:
    e = html.escape
    deals = _deals(j)
    sponsor = _SPONSOR_LABEL.get(j.sponsorship or "", "")
    score = f"{round(j.fit_score)}%" if j.fit_score is not None else "pending"
    parts = [
        f'<td style="padding:10px 8px;font-weight:700;color:#6366f1;white-space:nowrap">{score}</td>',
        '<td style="padding:10px 8px">'
        f'<a href="{job_url(j.id)}" style="color:#0f172a;font-weight:600;text-decoration:none">'
        f'{e(j.title or "?")}</a><br>'
        f'<span style="color:#64748b;font-size:13px">{e(j.company or "?")} — {e(j.location or "?")}</span>'
        + (f'<br><span style="color:#475569;font-size:13px">{e(j.ai_verdict)}</span>' if j.ai_verdict else "")
        + (f'<br><span style="color:#b91c1c;font-size:12px">⚠ {e("; ".join(deals))}</span>' if deals else "")
        + '</td>',
        f'<td style="padding:10px 8px;font-size:12px;color:#475569;white-space:nowrap">{sponsor}</td>',
        f'<td style="padding:10px 8px;white-space:nowrap">'
        f'<a href="{e(j.url or "#")}" style="color:#6366f1;font-size:13px">apply →</a></td>',
    ]
    return f'<tr style="border-bottom:1px solid #e2e8f0">{"".join(parts)}</tr>'


def build_digest(db, new_job_ids: list[int]) -> tuple[str, str] | None:
    """Return (subject, html_body), or None if there's nothing worth sending."""
    if not new_job_ids:
        return None
    jobs = db.query(Job).filter(Job.id.in_(new_job_ids)).all()
    return render_digest(jobs)


def render_digest(jobs: list) -> tuple[str, str] | None:
    """Pure render step — (subject, html) for a list of Job rows, or None."""
    if not jobs:
        return None

    jobs = sorted(jobs, key=_rank, reverse=True)
    strong = [j for j in jobs if j.fit_score is not None and j.fit_score >= STRONG_CUTOFF]
    shown = (strong or jobs)[:MAX_ROWS]

    subject = (
        f"JobHunter — {len(strong)} strong match{'es' if len(strong) != 1 else ''} "
        f"of {len(jobs)} new job{'s' if len(jobs) != 1 else ''}"
    )

    table = (
        '<table style="width:100%;border-collapse:collapse;font-size:14px">'
        + "".join(_row(j) for j in shown)
        + "</table>"
    )
    extra = len(jobs) - len(shown)
    footer = (
        f'<p style="color:#64748b;font-size:13px">+ {extra} more on the '
        f'<a href="{settings.frontend_url}/jobs" style="color:#6366f1">dashboard</a>.</p>'
        if extra > 0 else
        f'<p style="color:#64748b;font-size:13px">'
        f'<a href="{settings.frontend_url}/jobs" style="color:#6366f1">Open the dashboard →</a></p>'
    )

    body = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:0 auto;color:#0f172a">
  <h2 style="margin:0 0 4px">{len(jobs)} new job{'s' if len(jobs) != 1 else ''} today</h2>
  <p style="color:#64748b;margin:0 0 16px">
    Ranked by AI fit score. {len(strong)} scored {STRONG_CUTOFF}%+.
  </p>
  {table}
  {footer}
</div>"""
    return subject, body


def send_daily_digest(db, new_job_ids: list[int]) -> bool:
    """Build and send the digest. Returns True if an email went out."""
    if not settings.digest_enabled:
        return False
    if not (settings.gmail_from and settings.gmail_app_password):
        logger.info("digest skipped — Gmail not configured")
        return False
    built = build_digest(db, new_job_ids)
    if not built:
        logger.info("digest skipped — no new jobs")
        return False
    subject, body = built
    try:
        send_digest(settings.digest_recipient, subject, body)
        logger.info(f"📧 Digest sent to {settings.digest_recipient} — {subject}")
        return True
    except Exception as exc:
        logger.error(f"digest send failed: {exc}")
        return False
