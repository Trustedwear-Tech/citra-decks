"""
verification/critic_agent.py
============================
Second-pass LLM critic that scans an answer for sentences not directly
supported by the retrieved context. Used by:
- Main chat (orchestrator.verify_response node, gated by CRITIC_ENABLED)
- Composer / Action chat (Phase 6, opt-in per endpoint)

Design:
- Stateless. Pure function over (context, answer) → list of unsupported claims.
- Runs at temperature 0 — we want determinism, not creativity.
- Cost-aware: caller decides when to invoke (e.g. only on `low_signal`).
- Output is JSON; we tolerate model JSON drift with regex fallback.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from token_utils import truncate_to_token_limit

logger = logging.getLogger(__name__)

# Cost guard: skip critic if either side is huge.
CRITIC_MAX_CONTEXT_TOKENS = int(os.getenv("CRITIC_MAX_CONTEXT_TOKENS", "8000"))
CRITIC_MAX_ANSWER_TOKENS = int(os.getenv("CRITIC_MAX_ANSWER_TOKENS", "4000"))
# Default OFF: the critic is a probabilistic LLM-based check (~60-80% recall,
# 50-70% precision). Strict-grounding prefix + source-origin tagging + low
# temperature + reranker already do the heavy lifting deterministically.
# Opt-in via CRITIC_ENABLED=true for high-stakes deployments only.
CRITIC_ENABLED_DEFAULT = os.getenv("CRITIC_ENABLED", "false").lower() == "true"


CRITIC_SYSTEM_PROMPT = """You are a strict grounding critic. Your only job is to find sentences in the ANSWER that are NOT directly supported by the CONTEXT.

Rules:
- A sentence is "supported" if its factual claims (numbers, names, dates, quotes, identifiers, statistics, URLs) appear in the CONTEXT, or if the answer explicitly tags it `[general-knowledge]`.
- A sentence is "unsupported" if it makes a factual claim not present in the CONTEXT and not tagged `[general-knowledge]`.
- Stylistic phrasing, transitional sentences, and recap paragraphs are NOT unsupported on their own — only flag sentences with concrete factual claims that aren't grounded.
- Do not penalise short answers. Do not invent missing context.

Output ONLY a single JSON object, no prose:
{
  "unsupported": [
    {"sentence": "<exact sentence from answer>", "missing": "<what fact is unverifiable>"}
  ],
  "severity": "none" | "low" | "medium" | "high"
}

Severity guide:
- none: no unsupported claims
- low: 1 minor unsupported claim, no numbers/names/dates
- medium: 2-3 unsupported claims, or 1 with numbers/names/dates
- high: any unsupported number, date, citation, identifier, or 4+ unsupported sentences
"""


@dataclass
class CriticResult:
    severity: str = "none"          # none | low | medium | high
    unsupported: List[Dict[str, str]] = field(default_factory=list)
    ran: bool = False
    error: Optional[str] = None

    def has_problems(self) -> bool:
        return self.severity in {"medium", "high"} and bool(self.unsupported)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "unsupported_count": len(self.unsupported),
            "unsupported": self.unsupported,
            "ran": self.ran,
            "error": self.error,
        }


def _parse_critic_output(raw: str) -> CriticResult:
    """Best-effort JSON parsing with regex fallback."""
    if not raw:
        return CriticResult(severity="none", ran=True)

    # Try direct JSON
    try:
        obj = json.loads(raw.strip())
    except json.JSONDecodeError:
        # Try to find a JSON object in the text
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            logger.warning("⚠️ [CRITIC] could not parse JSON from critic output")
            return CriticResult(severity="none", ran=True, error="parse_failure")
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ [CRITIC] JSON parse failed: {e}")
            return CriticResult(severity="none", ran=True, error="parse_failure")

    severity = str(obj.get("severity", "none")).lower()
    if severity not in {"none", "low", "medium", "high"}:
        severity = "none"
    unsupported = obj.get("unsupported") or []
    if not isinstance(unsupported, list):
        unsupported = []
    cleaned: List[Dict[str, str]] = []
    for item in unsupported:
        if isinstance(item, dict) and item.get("sentence"):
            cleaned.append({
                "sentence": str(item.get("sentence", "")).strip(),
                "missing": str(item.get("missing", "")).strip(),
            })
    return CriticResult(severity=severity, unsupported=cleaned, ran=True)


def verify_answer(
    context: str,
    answer: str,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> CriticResult:
    """
    Run the critic. Returns a CriticResult with `ran=True` on success.

    Caller should typically gate this with `if context_quality.low_signal or
    severity_check_required:` to avoid doubling LLM cost on every turn.
    """
    if enabled is None:
        enabled = CRITIC_ENABLED_DEFAULT
    if not enabled:
        return CriticResult(severity="none", ran=False, error="disabled")

    if not (context and context.strip()) or not (answer and answer.strip()):
        return CriticResult(severity="none", ran=False, error="empty_input")

    # Lazy import to avoid circular dep with llm_oss.
    try:
        from llm_oss import llm_call
    except ImportError as e:  # pragma: no cover
        logger.error(f"❌ [CRITIC] llm_call import failed: {e}")
        return CriticResult(severity="none", ran=False, error="llm_unavailable")

    # Cost guard
    context_for_critic = truncate_to_token_limit(context, CRITIC_MAX_CONTEXT_TOKENS, label="critic_context")
    answer_for_critic = truncate_to_token_limit(answer, CRITIC_MAX_ANSWER_TOKENS, label="critic_answer")

    user_prompt = (
        "CONTEXT:\n"
        "============\n"
        f"{context_for_critic}\n"
        "============\n\n"
        "ANSWER (under review):\n"
        "============\n"
        f"{answer_for_critic}\n"
        "============\n\n"
        "Return the JSON object as instructed."
    )

    try:
        raw = llm_call(
            system_prompt=CRITIC_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            user_id=user_id,
            user_email=user_email,
            max_tokens=4000,
            temperature=0.0,
            json_mode=True,
        )
    except Exception as e:
        logger.error(f"❌ [CRITIC] LLM call failed: {e}")
        return CriticResult(severity="none", ran=False, error=f"llm_error: {e}")

    result = _parse_critic_output(raw or "")
    logger.info(
        f"🧐 [CRITIC] severity={result.severity} unsupported={len(result.unsupported)}"
    )
    return result
