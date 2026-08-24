# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""Regression: main chat is an ENTERPRISE-ONLY search surface.

Main chat (``/query/stream`` → ``stream_llm_response_impl``) searches the
organisation's governed sources: the ``dept_*`` MCP tools and the enterprise
SOP library. The personal vault — a user's own uploaded folders — is NOT a
source there:

  * the UI has no upload "+", no folder panel, no Data Store toggle
    (``Citra-UI/config/featureFlags.js`` → ``PERSONAL_VAULT_ENABLED``),
  * ``/query/stream`` forces ``use_personal_data=False`` regardless of what the
    client sent, and
  * ``list_vault_files`` / ``personal_data_tool`` are never registered as chat
    tools.

The composers (report / presentation / printable) and quick chat still read the
vault through their own code paths — this is scoped to main chat.

Static checks, matching the style of test_no_action_chat_redirect.py.
"""
from __future__ import annotations

import os


def _read(*parts):
    path = os.path.join(os.path.dirname(__file__), "..", *parts)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_ui(*parts):
    path = os.path.join(os.path.dirname(__file__), "..", "..", "Citra-UI", *parts)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


MAIN = _read("streaming_response.py")
QUERY = _read("query.py")


def test_main_chat_registers_no_vault_tools():
    """The vault tool schemas must not be added to the chat tool list."""
    assert "build_personal_data_tool_schema" not in MAIN, (
        "personal_data_tool schema re-imported into streaming_response.py — "
        "main chat must not offer a personal-vault tool"
    )
    assert "build_list_vault_files_tool_schema" not in MAIN, (
        "list_vault_files schema re-imported into streaming_response.py — "
        "main chat must not offer a personal-vault tool"
    )
    assert "personal_tool_enabled = False" in MAIN, (
        "streaming_response.py no longer hard-disables the personal vault tools"
    )


def test_main_chat_prompt_states_there_is_no_personal_store():
    """The model must be told the personal store is absent, not left to guess."""
    assert "NO PERSONAL DATA STORE ON THIS SURFACE" in MAIN, (
        "streaming_response.py lost the prompt block telling the LLM it has no "
        "personal data store — without it the model offers to check uploads it "
        "cannot read"
    )


def test_stream_endpoint_forces_personal_data_off():
    """A stale client bundle must not be able to switch the vault back on."""
    assert "use_personal_data = False" in QUERY, (
        "/query/stream no longer forces use_personal_data=False"
    )
    assert "folder_search_enabled = False" in QUERY, (
        "/query/stream no longer clears folder_search_enabled"
    )


def test_enterprise_sources_are_always_on():
    """Enterprise sources are the only sources left — they cannot be switched off.

    A stored ``use_enterprise_data=false`` would otherwise leave main chat with
    nothing to search. General Query (``model_only``) is the one honoured
    opt-out.
    """
    assert "enterprise_enabled = not _model_only" in QUERY, (
        "/query/stream no longer forces enterprise sources on — a stale "
        "use_enterprise_data=false would leave main chat with no data source"
    )
    assert 'payload.get(\'model_only\', False)' in QUERY, (
        "/query/stream stopped honouring model_only — General Query mode would "
        "silently still search enterprise sources"
    )


def test_ui_personal_vault_flag_is_off():
    flags = _read_ui("config", "featureFlags.js")
    assert "export const PERSONAL_VAULT_ENABLED = false;" in flags, (
        "PERSONAL_VAULT_ENABLED was turned back on — main chat would regain the "
        "upload '+', the folder panel and the Data Store source toggle"
    )
