"""Phase 6 — feedback loop. No network: llm.complete is monkeypatched."""
import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import ai_generator
import llm
import preferences
from database import Base, Job
from routes.jobs import FeedbackUpdate, update_feedback


def _session():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


_url_counter = [0]


def _rated(db, feedback, n, reason=None, verdict="ok"):
    for i in range(n):
        _url_counter[0] += 1
        db.add(Job(url=f"u{_url_counter[0]}", title=f"Job {i}", company="Acme",
                    location="Paris, FR", feedback=feedback, feedback_reason=reason,
                    ai_verdict=verdict))
    db.commit()


# ── PATCH /jobs/{id}/feedback ────────────────────────────────────────────────

def test_feedback_set_change_and_clear():
    db = _session()
    job = Job(url="u1", title="Backend Engineer")
    db.add(job)
    db.commit()

    update_feedback(job.id, FeedbackUpdate(feedback=1), db)
    db.refresh(job)
    assert job.feedback == 1 and job.feedback_reason is None

    update_feedback(job.id, FeedbackUpdate(feedback=-1, reason="Too senior"), db)
    db.refresh(job)
    assert job.feedback == -1 and job.feedback_reason == "Too senior"

    update_feedback(job.id, FeedbackUpdate(feedback=0), db)
    db.refresh(job)
    assert job.feedback is None and job.feedback_reason is None


def test_feedback_unknown_id_404():
    from fastapi import HTTPException
    db = _session()
    with pytest.raises(HTTPException) as exc:
        update_feedback(999, FeedbackUpdate(feedback=1), db)
    assert exc.value.status_code == 404


def test_feedback_rejects_bad_value():
    from fastapi import HTTPException
    db = _session()
    job = Job(url="u1", title="X")
    db.add(job)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        update_feedback(job.id, FeedbackUpdate(feedback=2), db)
    assert exc.value.status_code == 400


# ── preferences.build_note ───────────────────────────────────────────────────

def test_build_note_caps_at_600_chars_and_only_rated_jobs(monkeypatch):
    db = _session()
    _rated(db, 1, 3)
    _rated(db, -1, 2, reason="Wrong stack")
    db.add(Job(url="unrated", title="Not rated", company="X", location="Paris, FR"))
    db.commit()

    seen = {}

    async def fake_complete(prompt, tier="fast"):
        seen["prompt"] = prompt
        return "x" * 900, "p", "m"   # model ignores the length instruction

    monkeypatch.setattr(llm, "complete", fake_complete)
    note = asyncio.run(preferences.build_note(db))

    assert len(note) == 600
    assert "Not rated" not in seen["prompt"]
    assert "Wrong stack" in seen["prompt"]


def test_build_note_empty_when_nothing_rated(monkeypatch):
    db = _session()

    async def fail_complete(prompt, tier="fast"):
        raise AssertionError("should not call the LLM with nothing rated")

    monkeypatch.setattr(llm, "complete", fail_complete)
    assert asyncio.run(preferences.build_note(db)) == ""


# ── preferences.refresh caching ──────────────────────────────────────────────

def test_refresh_regenerates_after_5_new_ratings_not_before(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "PATH", tmp_path / "preferences.json")
    db = _session()
    _rated(db, 1, 3)

    calls = []

    async def fake_complete(prompt, tier="fast"):
        calls.append(1)
        return "note text", "p", "m"

    monkeypatch.setattr(llm, "complete", fake_complete)

    # 3 rated jobs < threshold of 5 from a baseline of 0 -> no LLM call yet
    note = asyncio.run(preferences.refresh(db))
    assert note == "" and calls == []

    _rated(db, -1, 2)  # now 5 rated total -> hits the threshold
    note = asyncio.run(preferences.refresh(db))
    assert note == "note text" and len(calls) == 1

    # one more rating (delta of 1 from the new baseline of 5) -> not enough yet
    _rated(db, 1, 1)
    note = asyncio.run(preferences.refresh(db))
    assert note == "note text" and len(calls) == 1  # unchanged, no new call


def test_refresh_llm_failure_keeps_previous_note(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "PATH", tmp_path / "preferences.json")
    db = _session()
    _rated(db, 1, 5)

    async def ok_complete(prompt, tier="fast"):
        return "good note", "p", "m"

    monkeypatch.setattr(llm, "complete", ok_complete)
    first = asyncio.run(preferences.refresh(db))
    assert first == "good note"

    _rated(db, -1, 5)  # enough new ratings to trigger another regen attempt

    async def broken_complete(prompt, tier="fast"):
        raise llm.LLMError("every provider failed")

    monkeypatch.setattr(llm, "complete", broken_complete)
    second = asyncio.run(preferences.refresh(db))
    assert second == "good note"  # scan keeps running with the old note
    assert preferences.get_note() == "good note"


# ── ai_generator._triage_prompt picks up the note ────────────────────────────

def test_triage_prompt_includes_note_when_present(monkeypatch, tmp_path):
    pref_path = tmp_path / "preferences.json"
    monkeypatch.setattr(preferences, "PATH", pref_path)
    pref_path.write_text('{"note": "Avoid senior roles.", "rated_count": 5}', encoding="utf-8")

    prompt = ai_generator._triage_prompt({}, [])
    assert "Avoid senior roles." in prompt
    assert "WHAT THIS CANDIDATE HAS SAID" in prompt


def test_triage_prompt_unchanged_without_note(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "PATH", tmp_path / "preferences.json")
    prompt = ai_generator._triage_prompt({}, [])
    assert "WHAT THIS CANDIDATE HAS SAID" not in prompt


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-v"]))
