"""Detect when a quick/main chat request should be redirected to Action Chat.

Quick Chat and the main ``/query/stream`` endpoint are built for Q&A and
enterprise-data retrieval; neither can produce a real presentation, a
multi-section report, or run a deep-research workflow (no skill system,
no image generation, no sandbox egress for image APIs). When the user
asks for one of those, we redirect the turn server-side to
``/actionchat/query/stream`` (which has all of that) and bridge the
stream back to the originating chat surface.

Detection is keyword + negative-pattern based — zero LLM cost, zero
extra latency, easy to audit. Two stages:

  1. ``_POSITIVE_PATTERNS`` — keyword groups that trigger a candidate
     redirect, each tagged with the intent name shown to the user
     ("presentation" / "report" / "deep_research").
  2. ``_NEGATIVE_PATTERNS`` — phrasings that look like the user is
     asking ABOUT an existing artifact ("summarize the report",
     "what's in this deck") rather than asking to CREATE one. When a
     negative pattern matches the surrounding window of the positive
     hit, the redirect is suppressed.

The classifier is deliberately conservative: false negatives (missed
redirects) degrade gracefully — the user gets the normal quick/main
chat answer, which already politely admits when it can't make a deck.
False positives (incorrect redirects) are worse — they hand a simple
question to a multi-minute sandbox session — so the negative-pattern
guards lean strict.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

Intent = Literal["presentation", "report", "deep_research"]


@dataclass(frozen=True)
class RedirectDecision:
    redirect: bool
    intent: Intent | None
    confidence: Literal["high", "medium", "low"]
    matched_phrase: str | None
    reason: str | None  # populated when redirect=False AFTER a positive hit (i.e. negative pattern suppressed it)


# --- positive triggers (regexes are compiled once at import) -----------------
#
# Each entry: (compiled_pattern, intent_label, confidence).
# Patterns are intentionally narrow — broad words like "report" only match
# when paired with action verbs ("create / build / generate / write a
# report"), to keep the false-positive rate down on phrasings like "report
# on the bug" or "report this issue".

def _re(pat: str) -> re.Pattern:
    return re.compile(pat, re.IGNORECASE)


# Verbs that signal "produce this for me" (vs. ask-about / summarize).
_CREATE_VERBS = (
    r"(?:create|build|make|generate|produce|prepare|draft|write|"
    r"compose|put together|need|want|give me|send me|email me|"
    r"design|deliver)"
)

_POSITIVE_PATTERNS: list[tuple[re.Pattern, Intent, str]] = [
    # ── Presentation ──────────────────────────────────────────────────
    (_re(rf"\b{_CREATE_VERBS}\s+(?:a\s+|an\s+|the\s+|me\s+)?"
         r"(?:new\s+|full\s+|complete\s+|comprehensive\s+|short\s+)?"
         r"(?:\w+\s+){0,3}"
         r"(?:presentation|slides?|slide deck|deck|ppt|pptx|powerpoint|"
         r"pitch deck|board deck|investor deck|keynote)\b"),
     "presentation", "high"),
    (_re(r"\b(?:presentation|slides?|slide deck|deck|ppt|pptx|powerpoint|"
         r"pitch deck|board deck|investor deck)\s+(?:on|about|for|covering)\b"),
     "presentation", "high"),

    # ── Report / long-form document ────────────────────────────────────
    (_re(rf"\b{_CREATE_VERBS}\s+(?:a\s+|an\s+|the\s+|me\s+)?"
         r"(?:new\s+|full\s+|complete\s+|comprehensive\s+|detailed\s+|long-?form\s+)?"
         r"(?:\w+\s+){0,3}"
         r"(?:report|whitepaper|white[- ]paper|memo|board memo|"
         r"analyst report|market analysis|industry report|"
         r"due diligence|brief|long[- ]form document|"
         r"executive summary)\b"),
     "report", "high"),
    (_re(r"\b(?:whitepaper|white[- ]paper|board memo|market analysis|"
         r"industry report|due diligence|long[- ]form report)\s+"
         r"(?:on|about|for|covering)\b"),
     "report", "high"),

    # ── Deep research ──────────────────────────────────────────────────
    (_re(r"\b(?:deep\s+(?:research|dive|analysis)|"
         r"comprehensive\s+(?:research|analysis|investigation)|"
         r"in[- ]depth\s+(?:research|analysis|investigation)|"
         r"thorough\s+(?:research|investigation))\b"),
     "deep_research", "high"),
    (_re(rf"\b{_CREATE_VERBS}\s+(?:a\s+|an\s+)?"
         r"(?:deep[- ]dive|deep[- ]?research)\b"),
     "deep_research", "high"),
]

# ── Negative patterns ────────────────────────────────────────────────────
#
# These match phrasings where a positive keyword shows up but the user is
# clearly asking ABOUT an existing artifact, not asking to create one.
# We test against a window of text around the positive match (the whole
# message is fine for short prompts).

_NEGATIVE_PATTERNS: list[re.Pattern] = [
    # Read / open / display / summarize the existing one
    _re(r"\b(?:read|open|show|display|view|render|preview|"
        r"summarize|summarise|summary of|"
        r"explain|describe|"
        r"analyze|analyse|review|"
        r"extract|parse|"
        r"translate|"
        r"what(?:'?s| is| does)(?: in| inside| about)?|"
        r"tell me about)\s+"
        r"(?:the|this|that|my|our|the uploaded|the attached)?\s*"
        r"(?:\w+\s+){0,3}"
        r"(?:presentation|slides?|deck|ppt|pptx|powerpoint|"
        r"report|whitepaper|memo|brief|document)\b"),

    # "From / in / based on / inside <existing-artifact>"
    _re(r"\b(?:from|in|inside|within|based on|according to)\s+"
        r"(?:the|this|that|my|our|the uploaded|the attached)\s+"
        r"(?:\w+\s+){0,3}"
        r"(?:presentation|slides?|deck|report|whitepaper|memo|brief|document)\b"),

    # "the report says / shows / mentions" — clearly a read on an existing one
    _re(r"\b(?:the|this|that|my|our)\s+"
        r"(?:\w+\s+){0,3}"
        r"(?:presentation|slides?|deck|report|whitepaper|memo|brief|document)\s+"
        r"(?:says|shows|mentions|states|notes|contains|covers|talks about|discusses|references)\b"),

    # "report this <X>" / "report a bug" — verb-noun pattern, not the artifact
    _re(r"\breport\s+(?:this|that|a|an|the)\s+"
        r"(?:bug|issue|error|problem|incident|crash|outage|"
        r"failure|defect|complaint|case)\b"),

    # "deck" used loosely (sundeck, observation deck, …)
    _re(r"\b(?:sun|observation|pool|roof|swimming|cruise|ship)\s*deck\b"),

    # "memo to <person>" — typically a short note, not a long-form report
    _re(r"\b(?:short|quick|small|brief|tiny)\s+memo\b"),
]


# Minimum message length to even bother — 1-word prompts can't legitimately
# trigger a multi-minute redirect.
_MIN_MESSAGE_CHARS = 12


def classify(message: str | None) -> RedirectDecision:
    """Return whether ``message`` should be redirected to Action Chat.

    Pure function — safe to call from anywhere, no I/O, no side effects.
    """
    if not message or not isinstance(message, str):
        return RedirectDecision(False, None, "low", None, None)

    text = message.strip()
    if len(text) < _MIN_MESSAGE_CHARS:
        return RedirectDecision(False, None, "low", None, None)

    # Cheap early reject — none of the positive trigger root words present
    # at all, skip the regex run entirely. This keeps the per-request
    # overhead in the single-digit-microseconds range for the 95% of
    # messages that never trigger.
    lower = text.lower()
    if not any(seed in lower for seed in (
        "present", "slide", "deck", "ppt", "powerpoint", "keynote",
        "report", "whitepaper", "white-paper", "white paper", "memo",
        "brief", "analysis", "research", "deep dive", "due diligence",
        "depth", "in-depth", "investigation", "thorough",
    )):
        return RedirectDecision(False, None, "low", None, None)

    for pattern, intent, confidence in _POSITIVE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        matched_phrase = m.group(0)

        # Negative-pattern suppression check. We run against the FULL
        # message — for short prompts (the common case) this is fast and
        # avoids window-boundary surprises.
        for neg in _NEGATIVE_PATTERNS:
            if neg.search(text):
                logger.info(
                    "[REDIRECT_INTENT] positive hit suppressed by negative "
                    "pattern; intent=%s phrase=%r neg=%r",
                    intent, matched_phrase, neg.pattern[:60],
                )
                return RedirectDecision(
                    redirect=False,
                    intent=intent,
                    confidence="low",
                    matched_phrase=matched_phrase,
                    reason=f"suppressed by negative pattern: {neg.pattern[:80]}",
                )

        logger.info(
            "[REDIRECT_INTENT] matched intent=%s confidence=%s phrase=%r",
            intent, confidence, matched_phrase,
        )
        return RedirectDecision(
            redirect=True,
            intent=intent,
            confidence=confidence,
            matched_phrase=matched_phrase,
            reason=None,
        )

    return RedirectDecision(False, None, "low", None, None)


def wants_builder(message: str | None, kind: Intent) -> bool:
    """True only when ``message`` is an explicit request to CREATE a
    deliverable of ``kind`` (``"presentation"`` or ``"report"``).

    Used to gate the ``make_presentation`` / ``make_report`` builder tools in
    quick chat and main chat so they are offered to the LLM ONLY when the user
    actually asked for that artifact — never on Q&A, "summarise the existing
    deck", or unrelated requests (e.g. "give me a sample JSON file"). Reuses
    the same positive-trigger + negative-guard classifier as the action-chat
    redirect, so the two paths can never disagree about what counts as a
    "make a presentation" ask.
    """
    decision = classify(message)
    return bool(decision.redirect and decision.intent == kind)


# Public surface for the user-facing notice the bridge emits before the
# action-chat stream starts. Keeping this here so it's a single source of
# truth across quick chat + main chat handlers.

def user_facing_notice(intent: Intent) -> str:
    """Return the inline message shown to the user when we redirect."""
    label = {
        "presentation": "presentation",
        "report": "report",
        "deep_research": "deep-research workflow",
    }[intent]
    return (
        f"🔀 Redirecting your request to **Deep Research Chat** — your "
        f"{label} needs the file-builder sandbox and image generation, which "
        f"this surface doesn't have. Hang tight, deep research turns "
        f"typically take 1–3 minutes."
    )
