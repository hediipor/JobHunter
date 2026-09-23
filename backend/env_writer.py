"""
Tiny .env reader/writer for the setup wizard — no new pip deps.
Preserves comments/ordering; replaces existing KEY=... lines in place,
appends new ones, skips empty appends.
"""
from pathlib import Path

_TEMPLATE = """# ── LLM providers (any one works; more = more free quota) ──
# Gemini runs CV/cover letters first; Groq runs job triage first.
GEMINI_API_KEY={GEMINI_API_KEY}
GROQ_API_KEY={GROQ_API_KEY}
OPENROUTER_API_KEY={OPENROUTER_API_KEY}

# ── Gmail (use an App Password, NOT your main password) ────
# Guide: https://support.google.com/accounts/answer/185833
GMAIL_APP_PASSWORD={GMAIL_APP_PASSWORD}
GMAIL_FROM={GMAIL_FROM}

# ── Optional: RapidAPI for JSearch (more job sources) ──────
RAPIDAPI_KEY={RAPIDAPI_KEY}

# ── App Settings ───────────────────────────────────────────
SCAN_INTERVAL_HOURS=48
MAX_JOBS_PER_SCAN=50
"""

_DEFAULT_KEYS = ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "GMAIL_APP_PASSWORD", "GMAIL_FROM", "RAPIDAPI_KEY"]


def read_env(path) -> dict[str, str]:
    path = Path(path)
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def write_env(path, updates: dict[str, str]) -> None:
    path = Path(path)

    if not path.exists():
        values = {k: (updates.get(k) or "") for k in _DEFAULT_KEYS}
        path.write_text(_TEMPLATE.format(**values), encoding="utf-8")
        return

    lines = path.read_text(encoding="utf-8").splitlines()
    remaining = dict(updates)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in remaining:
            value = remaining.pop(key)
            if value is not None:
                lines[i] = f"{key}={value}"

    for key, value in remaining.items():
        if value:
            lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
