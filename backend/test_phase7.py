"""Phase 7 — mock interview per job. No network: llm.complete is monkeypatched."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import llm
from ai_generator import InterviewParseError, interview_feedback, interview_questions
from database import Base, Job
from routes import jobs as jobs_route
from routes.jobs import InterviewAnswer, InterviewFeedbackRequest


def _session():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _job_with_profile(db, tmp_path):
    job = Job(url="u1", title="Backend Engineer", company="Acme", location="Paris, FR",
              description="Python, FastAPI")
    db.add(job)
    db.commit()
    profile = tmp_path / "profile.json"
    profile.write_text("{}", encoding="utf-8")
    return job, profile


# ── ai_generator.interview_questions ─────────────────────────────────────────

def test_interview_questions_parses_five(monkeypatch):
    async def fake_complete(prompt, tier="fast"):
        return json.dumps([f"Q{i}?" for i in range(5)]), "p", "m"
    monkeypatch.setattr(llm, "complete", fake_complete)

    questions = asyncio.run(interview_questions({}, {"title": "Backend Engineer"}))
    assert questions == [f"Q{i}?" for i in range(5)]


def test_interview_questions_wrong_count_raises(monkeypatch):
    async def fake_complete(prompt, tier="fast"):
        return json.dumps([f"Q{i}?" for i in range(4)]), "p", "m"
    monkeypatch.setattr(llm, "complete", fake_complete)

    with pytest.raises(InterviewParseError):
        asyncio.run(interview_questions({}, {}))


def test_interview_questions_non_array_raises(monkeypatch):
    async def fake_complete(prompt, tier="fast"):
        return json.dumps({"not": "a list"}), "p", "m"
    monkeypatch.setattr(llm, "complete", fake_complete)

    with pytest.raises(InterviewParseError):
        asyncio.run(interview_questions({}, {}))


# ── ai_generator.interview_feedback ──────────────────────────────────────────

def _fb(idx, verdict="strong", note="ok"):
    return {"question_index": idx, "verdict": verdict, "note": note}


def test_interview_feedback_matched_by_index_not_position(monkeypatch):
    qa = [{"question": f"Q{i}", "answer": f"A{i}"} for i in range(3)]

    async def fake_complete(prompt, tier="fast"):
        # returned out of order — matching must be by question_index, not position
        return json.dumps([_fb(2, "improve", "shallow"), _fb(0, "strong", "clear"), _fb(1, "strong", "good")]), "p", "m"
    monkeypatch.setattr(llm, "complete", fake_complete)

    result = asyncio.run(interview_feedback({}, {}, qa))
    assert [r["question_index"] for r in result] == [0, 1, 2]
    assert result[2]["verdict"] == "improve" and result[2]["note"] == "shallow"


def test_interview_feedback_missing_or_duplicate_index_raises(monkeypatch):
    qa = [{"question": "Q0", "answer": "A0"}, {"question": "Q1", "answer": "A1"}]

    async def fake_complete(prompt, tier="fast"):
        return json.dumps([_fb(0), _fb(0)]), "p", "m"  # duplicate 0, index 1 never shows up
    monkeypatch.setattr(llm, "complete", fake_complete)

    with pytest.raises(InterviewParseError):
        asyncio.run(interview_feedback({}, {}, qa))


# ── routes ────────────────────────────────────────────────────────────────────

def test_interview_route_404_unknown_job(monkeypatch, tmp_path):
    db = _session()
    monkeypatch.setattr(jobs_route, "settings", SimpleNamespace(profile_path=tmp_path / "profile.json"))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(jobs_route.interview(999, db))
    assert exc.value.status_code == 404


def test_interview_route_503_when_exhausted(monkeypatch, tmp_path):
    db = _session()
    job, profile = _job_with_profile(db, tmp_path)
    monkeypatch.setattr(jobs_route, "settings", SimpleNamespace(profile_path=profile))

    async def exhausted(prompt, tier="fast"):
        raise llm.AllProvidersExhausted("no quota")
    monkeypatch.setattr(llm, "complete", exhausted)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(jobs_route.interview(job.id, db))
    assert exc.value.status_code == 503


def test_interview_feedback_route_422_on_empty_answers(monkeypatch, tmp_path):
    db = _session()
    job, profile = _job_with_profile(db, tmp_path)
    monkeypatch.setattr(jobs_route, "settings", SimpleNamespace(profile_path=profile))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(jobs_route.interview_feedback_route(job.id, InterviewFeedbackRequest(answers=[]), db))
    assert exc.value.status_code == 422


def test_interview_feedback_route_404_unknown_job(monkeypatch, tmp_path):
    db = _session()
    monkeypatch.setattr(jobs_route, "settings", SimpleNamespace(profile_path=tmp_path / "profile.json"))
    body = InterviewFeedbackRequest(answers=[InterviewAnswer(question="Q", answer="A")])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(jobs_route.interview_feedback_route(999, body, db))
    assert exc.value.status_code == 404


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-v"]))
