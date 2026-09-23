import httpx
import pytest

import llm


@pytest.fixture(autouse=True)
def isolated_llm(monkeypatch, tmp_path):
    """No test touches the real data/llm_budget.json or shares locks/cooldowns across tests."""
    monkeypatch.setattr(llm, "BUDGET_PATH", tmp_path / "llm_budget.json")
    monkeypatch.setattr(llm, "_budget", {})
    monkeypatch.setattr(llm, "_locks", {})
    monkeypatch.setattr(llm, "_last_at", {})
    monkeypatch.setattr(llm, "_cooldown_until", {})


def fake_providers(monkeypatch, *names, rpm=6000, rpd=None):
    """Swap the real provider table for fakes, all in one tier order."""
    table = {n: llm.Provider(n, f"https://{n}.test/v1", "m", "key", rpm, rpd) for n in names}
    monkeypatch.setattr(llm, "_providers", lambda: table)
    monkeypatch.setattr(llm, "TIERS", {"fast": list(names), "quality": list(names)})
    return table


def resp(status, **kw) -> httpx.Response:
    """httpx.Response that raise_for_status() accepts (needs a request attached)."""
    return httpx.Response(status, request=httpx.Request("POST", "https://fake.test"), **kw)
