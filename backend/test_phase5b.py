"""Phase 5b follow-ups. No network: llm.complete is monkeypatched."""
import asyncio

import ai_generator
import llm
from matcher import profile_skills


def test_cv_prompt_asks_for_most_recent_role_only(monkeypatch):
    seen = {}

    async def fake_complete(prompt, tier="fast"):
        seen["prompt"] = prompt
        return "{}", "p", "m"

    monkeypatch.setattr(llm, "complete", fake_complete)
    asyncio.run(ai_generator.generate_cv_data({"experience": []}, {"title": "Dev"}))
    assert "most recent role" in seen["prompt"]


def test_profile_skills_ignores_string_values():
    prof = {"skills": {"languages": "Python, JS", "tools": ["Git", "Docker"]}}
    assert profile_skills(prof) == ["git", "docker"]
