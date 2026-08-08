"""
Tests for the three-tier LLM routing config.

Covers:
  * tier-specific env vars override legacy LLM_* fallback
  * legacy LLM_* values are reused when tier-specific vars are unset
  * unknown tier values are coerced to the default
  * get_llm_client returns *distinct* clients per tier (different base_urls)
  * get_llm_extra_body honours per-tier JSON and DeepSeek auto-override
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure Citra-Service root is importable when running tests from repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip every LLM_* var so each test starts from a known state."""
    for key in list(os.environ.keys()):
        if key.startswith("LLM_"):
            monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture(autouse=True)
def _reset_clients():
    """Drop cached clients so each test sees fresh instances."""
    import citra_llm as llm_client
    llm_client.reset_clients()
    yield
    llm_client.reset_clients()


# ---------------------------------------------------------------------------
# get_tier_config
# ---------------------------------------------------------------------------

def test_tier_specific_env_takes_precedence(monkeypatch):
    from llm.llm_tiers import get_tier_config

    monkeypatch.setenv("LLM_BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "legacy-key")
    monkeypatch.setenv("LLM_MODEL", "legacy-model")

    monkeypatch.setenv("LLM_LARGE_BASE_URL", "https://large.example/v1")
    monkeypatch.setenv("LLM_LARGE_API_KEY", "large-key")
    monkeypatch.setenv("LLM_LARGE_MODEL", "deepseek/deepseek-chat-v3.1")

    cfg = get_tier_config("large")
    assert cfg["base_url"] == "https://large.example/v1"
    assert cfg["api_key"] == "large-key"
    assert cfg["model"] == "deepseek/deepseek-chat-v3.1"


def test_legacy_env_used_when_tier_unset(monkeypatch):
    from llm.llm_tiers import get_tier_config

    monkeypatch.setenv("LLM_BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "legacy-key")
    monkeypatch.setenv("LLM_MODEL", "legacy-model")

    cfg = get_tier_config("small")
    assert cfg["base_url"] == "https://legacy.example/v1"
    assert cfg["api_key"] == "legacy-key"
    assert cfg["model"] == "legacy-model"


def test_missing_config_raises(monkeypatch):
    from llm.llm_tiers import get_tier_config
    with pytest.raises(ValueError):
        get_tier_config("medium")


# ---------------------------------------------------------------------------
# coerce_tier
# ---------------------------------------------------------------------------

def test_coerce_tier_normalises_known_values():
    from llm.llm_tiers import DEFAULT_TIER, coerce_tier
    assert coerce_tier("small") == "small"
    assert coerce_tier(" Medium ") == "medium"
    assert coerce_tier("LARGE") == "large"
    assert coerce_tier(None) == DEFAULT_TIER
    assert coerce_tier("xyz") == DEFAULT_TIER


# ---------------------------------------------------------------------------
# get_llm_client — different base_urls produce different clients
# ---------------------------------------------------------------------------

def test_distinct_clients_per_tier(monkeypatch):
    from citra_llm import get_llm_client

    monkeypatch.setenv("LLM_SMALL_BASE_URL", "https://small.example/v1")
    monkeypatch.setenv("LLM_SMALL_API_KEY", "sk-small")
    monkeypatch.setenv("LLM_SMALL_MODEL", "z-ai/glm-4.7-flash")

    monkeypatch.setenv("LLM_LARGE_BASE_URL", "https://openrouter.example/v1")
    monkeypatch.setenv("LLM_LARGE_API_KEY", "sk-large")
    monkeypatch.setenv("LLM_LARGE_MODEL", "z-ai/glm-5.1")

    small = get_llm_client(tier="small")
    large = get_llm_client(tier="large")
    small_again = get_llm_client(tier="small")

    assert small is not large, "small/large clients must be distinct"
    assert small is small_again, "same-tier client must be cached"
    assert str(small.base_url).startswith("https://small.example")
    assert str(large.base_url).startswith("https://openrouter.example")


# ---------------------------------------------------------------------------
# get_llm_extra_body
# ---------------------------------------------------------------------------

def test_extra_body_per_tier_json(monkeypatch):
    from citra_llm import get_llm_extra_body

    monkeypatch.setenv("LLM_BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("LLM_MODEL", "legacy-model")

    # Use a non-reasoning model + non-OpenRouter base_url so neither the
    # reasoning override nor nitro routing injects anything — isolates the
    # "env EXTRA_BODY JSON is parsed and returned verbatim" behaviour.
    monkeypatch.setenv("LLM_MEDIUM_BASE_URL", "https://medium.example/v1")
    monkeypatch.setenv("LLM_MEDIUM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv(
        "LLM_MEDIUM_EXTRA_BODY",
        json.dumps({"provider": {"order": ["z-ai"]}}),
    )

    body = get_llm_extra_body(tier="medium")
    assert body == {"provider": {"order": ["z-ai"]}}


def test_reasoning_effort_default_on_glm(monkeypatch):
    """A reasoning-mode model (GLM) gets a default `reasoning.effort=low`
    injected; a non-reasoning model does not. Default is `low` for fast
    latency across the platform; surfaces that need deeper deliberation
    (action-chat, smart-app) set `effort=medium` explicitly in their
    LLM_<TIER>_EXTRA_BODY.
    """
    from citra_llm import get_llm_extra_body

    monkeypatch.setenv("LLM_LARGE_BASE_URL", "https://openrouter.example/v1")
    monkeypatch.setenv("LLM_LARGE_MODEL", "z-ai/glm-5.1")

    monkeypatch.setenv("LLM_SMALL_BASE_URL", "https://small.example/v1")
    monkeypatch.setenv("LLM_SMALL_MODEL", "gpt-4o-mini")

    large_body = get_llm_extra_body(tier="large")
    assert large_body.get("reasoning", {}).get("effort") == "low"

    small_body = get_llm_extra_body(tier="small")
    assert "reasoning" not in small_body
