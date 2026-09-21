"""Phase 5: matcher uses the profile it's given; overlapping scans are single-flight;
CV bullets aren't repeated under every role."""
import asyncio

import scan_service
from matcher import calculate_match


def test_matcher_scores_against_the_passed_profile():
    job = {"title": "Engineer", "description": "We use Rust and C++ daily."}
    rust = {"skills": {"languages": ["Rust", "C++"]}}
    py = {"skills": {"languages": ["Python"]}}
    s_rust, why_rust = calculate_match(job, rust)
    s_py, why_py = calculate_match(job, py)
    assert s_rust > s_py                       # 8 pts of skill match vs none
    assert "Matching skills: Rust, C++" in why_rust
    assert not any(r.startswith("Matching skills") for r in why_py)
    assert calculate_match(job, None)[0] == s_py  # no profile -> no skill points


def test_second_concurrent_scan_returns_immediately(monkeypatch):
    calls = []

    async def fake_run(session_factory):
        calls.append(1)
        await asyncio.sleep(0.05)
        return [1, 2]

    monkeypatch.setattr(scan_service, "_run_scan", fake_run)

    async def both():
        return await asyncio.gather(scan_service.scan_and_store(None), scan_service.scan_and_store(None))

    first, second = asyncio.run(both())
    assert first == [1, 2]
    assert second is None
    assert len(calls) == 1                      # the second never scraped
    assert scan_service.get_scan_state()["running"] is False


def test_cv_bullets_differ_per_role(tmp_path):
    from pdf_builder import build_cv_pdf
    import pdf_builder

    seen = []
    orig = pdf_builder.Paragraph
    monkey = lambda text, style: (seen.append(text), orig(text, style))[1]
    pdf_builder.Paragraph = monkey
    try:
        profile = {"name": "A", "email": "e", "phone": "p", "portfolio": "x", "linkedin": "l",
                   "experience": [{"role": "R1", "bullets": ["first-own"]},
                                  {"role": "R2", "bullets": ["second-own"]}]}
        build_cv_pdf(profile, {"key_achievements": ["tailored"]}, tmp_path / "cv.pdf")
    finally:
        pdf_builder.Paragraph = orig
    bullets = [t for t in seen if t.startswith("• ")]
    assert bullets == ["• tailored", "• second-own"]
