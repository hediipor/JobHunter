# JobHunter AI

A personal job/internship hunting assistant. It scrapes job postings (via the
[JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) API and a
Keejob.com scraper), scores them against your profile, generates a tailored
CV and cover letter with Google Gemini, and sends the application email —
all from a FastAPI backend and a Next.js dashboard.

## Setup

### 1. Backend

```bash
cd backend
python -m venv ../.venv
../.venv/Scripts/activate  # Windows; use `source ../.venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
```

Copy `.env.example` to `.env` in the project root and fill in:

- `GEMINI_API_KEY` — [Google AI Studio](https://aistudio.google.com/apikey)
- `GMAIL_APP_PASSWORD` — a [Gmail App Password](https://support.google.com/accounts/answer/185833) (not your login password)
- `RAPIDAPI_KEY` — subscribe to [JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) (free tier: 200 requests/month)

Copy `profile/profile.example.json` to `profile/profile.json` and fill in
your own name, contact details, education, experience, projects, and skills
— this is what the matcher scores jobs against and what Gemini uses to
generate your CV and cover letter.

Run the API:

```bash
uvicorn main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## How it works

1. **Scan** — pulls postings from JSearch (LinkedIn, Indeed, Glassdoor, and
   more) and Keejob.com, deduplicated by URL, on a schedule you set in the
   Settings page (default: every 24h).
2. **Match score** — each job gets a 0–100 score against your profile based
   on skill keywords, title relevance, experience level, and language match.
3. **Generate** — Gemini tailors a CV and cover letter to the specific job
   (using only what's in your profile — it won't invent experience), turned
   into ATS-friendly PDFs.
4. **Apply** — sends the application email with both PDFs attached via
   Gmail SMTP.

Track everything — new jobs, generated documents, sent applications,
interview/offer status — from the dashboard.
