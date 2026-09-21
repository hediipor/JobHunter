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

    async def post(p, prompt, timeout):
        calls.append(p.name)
        if p.name == "first":
            return DAILY_429
        return resp(200, json={"choices": [{"message": {"content": "hi"}}]})
    monkeypatch.setattr(llm, "_post", post)
    return calls


def test_daily_quota_falls_through_and_is_not_retried(two):
    assert asyncio.run(llm.complete("p", tier="fast")) == ("hi", "second", "m")
    assert two == ["first", "second"]

    assert asyncio.run(llm.complete("p", tier="fast")) == ("hi", "second", "m")
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


def test_fast_tier_leaves_reserve_for_quality(monkeypatch):
    table = fake_providers(monkeypatch, "groq", "gemini")
    table["groq"].rpd = 1
    table["gemini"].rpd = 20
    llm._entry("groq")["count"] = 1                    # groq is spent
    llm._entry("gemini")["count"] = 14                 # 20 - QUALITY_RESERVE["gemini"]
    calls = []

    async def post(p, prompt, timeout):
        calls.append(p.name)
        return resp(200, json={"choices": [{"message": {"content": "ok"}}]})
    monkeypatch.setattr(llm, "_post", post)

    with pytest.raises(llm.AllProvidersExhausted):
        asyncio.run(llm.complete("p", tier="fast"))
    assert calls == []                                 # gemini never posted to
    assert asyncio.run(llm.complete("p", tier="quality")) == ("ok", "gemini", "m")


def test_per_minute_429_waits_and_retries(monkeypatch):
    fake_providers(monkeypatch, "only")
    responses = [resp(429, headers={"retry-after": "0"}, text="tokens per minute (TPM)"),
                 resp(200, json={"choices": [{"message": {"content": "ok"}}]})]

    async def post(p, prompt, timeout):
        return responses.pop(0)
    monkeypatch.setattr(llm, "_post", post)
    monkeypatch.setattr(llm, "_retry_after", lambda *a: 0)
    assert asyncio.run(llm.complete("p", tier="fast")) == ("ok", "only", "m")
    assert not llm._budget["only"]["exhausted_until"]


def test_non_quota_failure_is_llm_error(monkeypatch):
    fake_providers(monkeypatch, "only")

    async def post(p, prompt, timeout):
        return resp(500)
    monkeypatch.setattr(llm, "_post", post)
    with pytest.raises(llm.LLMError):
        asyncio.run(llm.complete("p", tier="fast"))


def test_outage_puts_provider_on_cooldown(monkeypatch):
    """A timeout skips that provider on the next call — no second 45s hang —
    until the cooldown expires."""
    fake_providers(monkeypatch, "slow", "backup")
    calls = []

    async def post(p, prompt, timeout):
        calls.append(p.name)
        if p.name == "slow":
            raise llm.httpx.ReadTimeout("hung")
        return resp(200, json={"choices": [{"message": {"content": "ok"}}]})
    monkeypatch.setattr(llm, "_post", post)

    assert asyncio.run(llm.complete("p", tier="fast")) == ("ok", "backup", "m")
    assert asyncio.run(llm.complete("p", tier="fast")) == ("ok", "backup", "m")
    assert calls == ["slow", "backup", "backup"]      # skipped while cooling down

    monkeypatch.setattr(llm, "_cooldown_until", {"slow": 0})  # cooldown over
    asyncio.run(llm.complete("p", tier="fast"))
    assert calls[-2:] == ["slow", "backup"]


def test_quota_429_is_not_a_cooldown(two):
    asyncio.run(llm.complete("p", tier="fast"))
    assert "first" not in llm._cooldown_until


def test_tokens_counted_toward_daily_cap(monkeypatch):
    """Groq's binding limit is tokens/day, not requests/day."""
    table = fake_providers(monkeypatch, "only")
    table["only"].tpd = 1000

    async def post(p, prompt, timeout):
        return resp(200, json={"choices": [{"message": {"content": "ok"}}],
                               "usage": {"total_tokens": 600}})
    monkeypatch.setattr(llm, "_post", post)
    asyncio.run(llm.complete("p", tier="fast"))
    asyncio.run(llm.complete("p", tier="fast"))        # 1200 >= 1000
    assert llm.status()[0]["tokens_today"] == 1200
    with pytest.raises(llm.AllProvidersExhausted):
        asyncio.run(llm.complete("p", tier="fast"))
