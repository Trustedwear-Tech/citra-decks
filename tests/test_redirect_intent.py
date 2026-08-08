"""Unit tests for ``services.redirect_intent``.

Pure-function classifier — no I/O, fast, deterministic. Covers:
  - Positive intents (presentation / report / deep_research)
  - Negative-pattern suppression (asking ABOUT an existing artifact)
  - False-positive guards (loose words like "deck", "report this bug")
  - Edge cases (empty / very short / non-string inputs)
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.redirect_intent import classify, user_facing_notice  # noqa: E402


# ─── positive cases — must redirect ──────────────────────────────────────────

@pytest.mark.parametrize("message,expected_intent", [
    # Presentation triggers
    ("create a presentation on bird life", "presentation"),
    ("Make me a slide deck about Q4 sales", "presentation"),
    ("build a pitch deck for investors", "presentation"),
    ("generate a powerpoint about the migration project", "presentation"),
    ("I need a board deck covering the FY27 plan", "presentation"),
    ("can you put together slides on competitor analysis", "presentation"),
    ("design a keynote for tomorrow's all-hands", "presentation"),
    ("PPT on the new product launch", "presentation"),
    ("presentation on the supply chain risks", "presentation"),

    # Report triggers
    ("write a comprehensive report on market trends", "report"),
    ("create a whitepaper about our AI strategy", "report"),
    ("draft a board memo on the acquisition", "report"),
    ("I want a long-form report on customer churn", "report"),
    ("prepare a market analysis on the EU expansion", "report"),
    ("generate a due diligence brief on Vendor X", "report"),
    ("whitepaper on zero-trust architecture", "report"),

    # Deep research triggers
    ("do a deep research on India's solar industry", "deep_research"),
    ("I need a comprehensive analysis of competitor pricing", "deep_research"),
    ("run an in-depth investigation into the supply chain", "deep_research"),
    ("perform thorough research on the regulatory landscape", "deep_research"),
    ("give me a deep dive on the customer cohort retention", "deep_research"),
])
def test_positive_redirects(message: str, expected_intent: str):
    decision = classify(message)
    assert decision.redirect, f"expected redirect for {message!r} but got {decision}"
    assert decision.intent == expected_intent, (
        f"expected intent {expected_intent} but got {decision.intent}"
    )
    assert decision.matched_phrase, "should expose the matched phrase"
    assert decision.confidence in ("high", "medium")


# ─── negative-pattern suppression — must NOT redirect ────────────────────────

@pytest.mark.parametrize("message", [
    "summarize the report I just uploaded",
    "what does this presentation say about Q4?",
    "show me the slide titles from the deck",
    "extract data from the whitepaper",
    "read the report and tell me the conclusions",
    "what's inside this powerpoint file",
    "from the uploaded report, what is the EBITDA?",
    "in this deck, which slide covers revenue?",
    "the report says that we should expand — what's the reasoning?",
    "the presentation mentions a 2030 target — find it",
    "based on the memo, what should we do next?",
    "translate the slides from English to French",
    "review the report I shared earlier",
    "explain the deck I sent you",
    "preview the powerpoint",
])
def test_negative_patterns_suppress_redirect(message: str):
    decision = classify(message)
    assert not decision.redirect, (
        f"expected NO redirect for {message!r} but got {decision}"
    )


# ─── false-positive guards ───────────────────────────────────────────────────

@pytest.mark.parametrize("message", [
    "report this bug to the team",
    "I want to report an issue with the login flow",
    "please report a crash in the mobile app",
    "report the outage to engineering",
    "we stood on the sun deck during the cruise",
    "the observation deck has a great view",
    "send a short memo to the team",
    "quick memo: please review the design",
    # Just naming a file extension without action
    "pdf",
    "ppt",
    # Very short prompts that legitimately can't trigger
    "hi",
    "thanks",
    "ok",
    "presentation",
    "slides?",
    "",
    "   ",
])
def test_no_redirect_on_loose_or_short_input(message: str):
    decision = classify(message)
    assert not decision.redirect, (
        f"expected NO redirect for {message!r} but got {decision}"
    )


# ─── neutral Q&A — must NOT redirect ─────────────────────────────────────────

@pytest.mark.parametrize("message", [
    "what's the capital of France?",
    "what is 2 + 2?",
    "summarize this document",
    "find me the latest news on AI",
    "search for posts about Python tutorials",
    "convert this CSV to Excel",
    "extract the tables from this PDF",
    "translate this paragraph to Spanish",
    "what files do I have uploaded?",
    "list all my folders",
])
def test_neutral_queries_do_not_redirect(message: str):
    decision = classify(message)
    assert not decision.redirect


# ─── edge cases ──────────────────────────────────────────────────────────────

def test_none_input():
    assert classify(None).redirect is False


def test_non_string_input():
    assert classify(12345).redirect is False  # type: ignore[arg-type]
    assert classify(["build a deck"]).redirect is False  # type: ignore[arg-type]


def test_decision_is_immutable():
    d = classify("create a presentation on bird life")
    with pytest.raises(Exception):
        d.redirect = False  # type: ignore[misc]  # frozen dataclass


# ─── user_facing_notice ──────────────────────────────────────────────────────

@pytest.mark.parametrize("intent,fragment", [
    ("presentation", "presentation"),
    ("report", "report"),
    ("deep_research", "deep-research"),
])
def test_user_facing_notice_mentions_intent(intent: str, fragment: str):
    msg = user_facing_notice(intent)  # type: ignore[arg-type]
    assert "Deep Research" in msg
    assert fragment in msg
