"""llm.complete() routing: fallthrough on daily quota, no same-day retry,
budget persisted to disk, AllProvidersExhausted when everything is spent.
No network: llm._post is monkeypatched."""
import asyncio

import pytest

import llm
from conftest import fake_providers, resp

DAILY_429 = resp(429, text="Rate limit reached for model on requests per day (RPD): Limit 1000")


@pytest.fixture
def two(monkeypatch):
    """'first' is out for the day; 'second' answers."""
    fake_providers(monkeypatch, "first", "second")
    calls = []

    async def post(p, prompt):
        calls.append(p.name)
        if p.name == "first":
            return DAILY_429
        return resp(200, json={"choices": [{"message": {"content": "hi"}}]})
    monkeypatch.setattr(llm, "_post", post)
    return calls


def test_daily_quota_falls_through_and_is_not_retried(two):
    assert asyncio.run(llm.complete("p", tier="fast")) == ("hi", "second")
    assert two == ["first", "second"]

    assert asyncio.run(llm.complete("p", tier="fast")) == ("hi", "second")
    assert two == ["first", "second", "second"]  # 'first' skipped for the rest of the day


def test_budget_survives_reload(two, monkeypatch):
    asyncio.run(llm.complete("p", tier="quality"))
    monkeypatch.setattr(llm, "_budget", llm._load())  # simulate a restart
    assert llm._budget["first"]["exhausted_until"]
    assert llm._budget["second"]["count"] == 1

    asyncio.run(llm.complete("p", tier="quality"))
    assert two == ["first", "second", "second"]
    assert llm._budget["second"]["count"] == 2


def test_date_rollover_resets(two, monkeypatch):
    asyncio.run(llm.complete("p", tier="fast"))
    later = llm._now() + llm.dt.timedelta(days=1)
    monkeypatch.setattr(llm, "_now", lambda: later)
    asyncio.run(llm.complete("p", tier="fast"))
    assert two[-2:] == ["first", "second"]  # 'first' tried again the next UTC day


def test_all_exhausted(two, monkeypatch):
    fake_providers(monkeypatch, "first", "second", rpd=1)
    asyncio.run(llm.complete("p", tier="fast"))        # 'first' dies, 'second' hits its cap of 1
    with pytest.raises(llm.AllProvidersExhausted):
        asyncio.run(llm.complete("p", tier="fast"))
    assert two == ["first", "second"]                  # nothing was even attempted


def test_per_minute_429_waits_and_retries(monkeypatch):
    fake_providers(monkeypatch, "only")
    responses = [resp(429, headers={"retry-after": "0"}, text="tokens per minute (TPM)"),
                 resp(200, json={"choices": [{"message": {"content": "ok"}}]})]

    async def post(p, prompt):
        return responses.pop(0)
    monkeypatch.setattr(llm, "_post", post)
    monkeypatch.setattr(llm, "_retry_after", lambda *a: 0)
    assert asyncio.run(llm.complete("p", tier="fast")) == ("ok", "only")
    assert not llm._budget["only"]["exhausted_until"]


def test_non_quota_failure_is_llm_error(monkeypatch):
    fake_providers(monkeypatch, "only")

    async def post(p, prompt):
        return resp(500)
    monkeypatch.setattr(llm, "_post", post)
    with pytest.raises(llm.LLMError):
        asyncio.run(llm.complete("p", tier="fast"))
