# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""Regression: chat surfaces must NOT redirect to action-chat.

The legacy path that proxied presentation / report / deep-research requests to
action-chat (both the regex preflight and the ``deep_research_handoff`` LLM
tool) was removed from quick chat and main chat. Presentations now build via
``make_presentation`` (presentation composer UI) and reports via
``make_report`` (printable UI) — in-place, grounded on the user's selected
vault. Deep-research asks are answered inline by the normal loop.

These static checks guard against the legacy wiring creeping back.
"""
from __future__ import annotations

import os


def _read(*parts):
    path = os.path.join(os.path.dirname(__file__), "..", *parts)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


QUICK = _read("api", "quick_chat.py")
MAIN = _read("streaming_response.py")
QUERY = _read("query.py")


def test_no_deep_research_handoff_tool_or_handler():
    for src, name in ((QUICK, "quick_chat.py"), (MAIN, "streaming_response.py")):
        assert '"name": "deep_research_handoff"' not in src, (
            f"deep_research_handoff tool definition still present in {name}"
        )
        assert 'elif fn_name == "deep_research_handoff":' not in src, (
            f"deep_research_handoff dispatch branch still present in {name}"
        )


def test_no_action_chat_bridge_usage():
    for src, name in (
        (QUICK, "quick_chat.py"),
        (MAIN, "streaming_response.py"),
        (QUERY, "query.py"),
    ):
        assert "from services.action_chat_bridge import bridge_to_action_chat" not in src, (
            f"action-chat bridge import still present in {name}"
        )
        assert "bridge_to_action_chat(" not in src, (
            f"action-chat bridge is still called in {name}"
        )


def test_no_redirect_stage_event():
    for src, name in (
        (QUICK, "quick_chat.py"),
        (MAIN, "streaming_response.py"),
        (QUERY, "query.py"),
    ):
        assert '"redirected_to_action_chat"' not in src, (
            f"redirect-to-action-chat stage event still emitted in {name}"
        )


def test_builder_tools_still_present_in_quick_chat():
    """Quick chat keeps the in-place composer builder tools."""
    assert '"name": "make_presentation"' in QUICK, (
        "make_presentation tool missing from quick_chat.py"
    )
    assert '"name": "make_report"' in QUICK, (
        "make_report tool missing from quick_chat.py"
    )
    assert 'elif fn_name in ("make_presentation", "make_report"):' in QUICK, (
        "builder dispatch branch missing from quick_chat.py"
    )


def test_main_chat_has_no_builder_tools():
    """Main chat is DISCONNECTED from the presentation / printable composers.

    Typing "create a presentation" or "write a report" in main chat must answer
    inline — it must never launch the presentation or printable UI. The home
    cards for those surfaces are hidden too (Citra-UI/config/
    operationsCapabilities.js → hiddenOnHome), so the tools must not creep back.
    """
    assert '"name": "make_presentation"' not in MAIN, (
        "make_presentation tool re-added to streaming_response.py (main chat)"
    )
    assert '"name": "make_report"' not in MAIN, (
        "make_report tool re-added to streaming_response.py (main chat)"
    )
    assert 'elif fn_name in ("make_presentation", "make_report"):' not in MAIN, (
        "builder dispatch branch re-added to streaming_response.py (main chat)"
    )
    assert "StreamEventType.OPEN_BUILDER," not in MAIN, (
        "streaming_response.py yields OPEN_BUILDER again — main chat must not "
        "hand off to a composer UI"
    )
    assert "prepare_builder_handoff" not in MAIN, (
        "builder handoff re-imported into streaming_response.py (main chat)"
    )
