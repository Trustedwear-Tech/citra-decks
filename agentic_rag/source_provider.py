#!/usr/bin/env python3
# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Common Source Provider — single-purpose after the agentic-tool refactor.

Used to be a fan-out router across personal / enterprise (general/entity) /
saas Milvus sources for the orchestrator's pre-fetch phase. After the
refactor:

  • Personal vault retrieval is AGENTIC — chat LLM calls
    `personal_data_tool` (services/personal_data_tool.py).
  • Enterprise data is AGENTIC — chat LLM calls `dept_*` MCP tools
    (services/enterprise_tools.py).
  • Only the SaaSDataTool (file-listing metadata from Mongo) still runs
    as a pre-fetch — small payload, tells the LLM what files exist in
    the user's vault before it decides to call `personal_data_tool`.

This module now exists to (a) keep the orchestrator's call site unchanged
and (b) provide a single place to evolve the file-metadata pre-fetch
without sprawling logic. If/when the file-metadata pre-fetch also moves
into a tool, this whole module can be deleted.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .tools import RETRIEVAL_TOOLS

if TYPE_CHECKING:
    from .orchestrator import RetrievalStrategy

logger = logging.getLogger(__name__)


@dataclass
class SourceConfig:
    """Configuration for the file-metadata pre-fetch.

    Personal-vault and enterprise retrieval used to live here too; both are
    now agentic (LLM-callable tools), so this struct is intentionally tiny.
    """
    use_saas: bool = True  # File metadata listing (Mongo). Default on.
    selected_folder_ids: List[str] = field(default_factory=list)
    folder_search_enabled: bool = False
    persona_data: Optional[Dict[str, Any]] = None
    additional_kwargs: Dict[str, Any] = field(default_factory=dict)


class SourceProvider:
    """Pre-fetch source provider — SaaSDataTool only.

    Personal/enterprise retrieval was removed when those moved to LLM
    tool-loops. The file-metadata pre-fetch stays because the LLM needs
    to see what files exist before it decides what to query.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @property
    def saas_tool(self):
        return RETRIEVAL_TOOLS["saas"]

    # ────────────────────────────────────────────────────────────────────
    # Config builder — single shape regardless of how the orchestrator
    # phrased the request (strategy / state / multi-hop). All three legacy
    # builders collapsed into one because the only tunable left is folders.
    # ────────────────────────────────────────────────────────────────────

    def build_source_config(
        self,
        state: Dict[str, Any],
        *,
        use_saas: Optional[bool] = None,
    ) -> SourceConfig:
        """Build a SourceConfig from orchestrator state.

        ``use_saas`` defaults to ``state.get('use_saas_data', True)`` — the
        UI's file-metadata toggle. Pass ``False`` to skip the pre-fetch
        entirely (e.g. greetings / non-RAG turns where the planner has
        already determined no data is needed).
        """
        metadata = state.get("metadata", {}) or {}
        cfg_use_saas = state.get("use_saas_data", True) if use_saas is None else use_saas
        return SourceConfig(
            use_saas=bool(cfg_use_saas),
            selected_folder_ids=metadata.get("selected_folder_ids", []) or [],
            folder_search_enabled=bool(metadata.get("folder_search_enabled", False)),
            persona_data=state.get("persona_data"),
            additional_kwargs={
                "max_results": metadata.get("max_results", 10),
                "similarity_threshold": metadata.get("similarity_threshold"),
            },
        )

    # Back-compat aliases — orchestrator.py still calls these names. Keep
    # them as thin wrappers so the call sites don't have to change all at
    # once. Strategy-based routing has no surviving distinction since the
    # only enabled source is `saas`.
    def build_source_config_from_state(self, state: Dict[str, Any]) -> SourceConfig:
        return self.build_source_config(state)

    def build_source_config_from_strategies(
        self,
        strategies: List["RetrievalStrategy"],
        state: Dict[str, Any],
    ) -> SourceConfig:
        return self.build_source_config(state)

    # ────────────────────────────────────────────────────────────────────
    # Retrieval — now SaaSDataTool only.
    # ────────────────────────────────────────────────────────────────────

    async def retrieve_from_sources(
        self,
        query: str,
        user_id: str,
        source_config: SourceConfig,
        context_label: str = "retrieval",
        user_email: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Pre-fetch file-listing metadata from Mongo via SaaSDataTool.

        Returns ``{'saas': [chunks]}`` (other source keys removed). When
        ``use_saas=False`` returns an empty dict so the orchestrator can
        skip downstream merging.
        """
        contexts_by_source: Dict[str, List[Dict[str, Any]]] = {}
        if not source_config.use_saas:
            self.logger.info(f"⏭️  {context_label.title()} — SaaS prefetch disabled by config")
            return contexts_by_source

        self.logger.info(
            f"🔄 {context_label.title()} — fetching file-listing metadata "
            f"(folders={source_config.selected_folder_ids or 'all'})"
        )
        saas_kwargs = dict(source_config.additional_kwargs)
        # File metadata is small; keep result count modest.
        saas_kwargs["max_results"] = min(int(saas_kwargs.get("max_results", 20) or 20), 20)
        saas_kwargs["folder_ids"] = source_config.selected_folder_ids or []

        try:
            results = await self.saas_tool.retrieve(
                query=query,
                user_id=user_id,
                **saas_kwargs,
            )
            results = results if isinstance(results, list) else []
            for ctx in results:
                if isinstance(ctx, dict) and "source" not in ctx:
                    ctx["source"] = "saas"
            contexts_by_source["saas"] = results
            self.logger.info(
                f"   ✅ saas: {len(results)} file-metadata chunks"
            )
        except Exception as exc:
            self.logger.error(f"   ❌ saas retrieval failed: {exc}")
            contexts_by_source["saas"] = []

        return contexts_by_source

    # ────────────────────────────────────────────────────────────────────
    # Helpers retained for orchestrator compatibility
    # ────────────────────────────────────────────────────────────────────

    def merge_source_contexts(
        self,
        contexts_by_source: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """Merge contexts from all sources into a single list."""
        all_contexts: List[Dict[str, Any]] = []
        for source, contexts in contexts_by_source.items():
            for ctx in contexts:
                if isinstance(ctx, dict):
                    ctx.setdefault("source", source)
                    all_contexts.append(ctx)
        return all_contexts

    def get_source_summary(
        self, contexts_by_source: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, int]:
        return {source: len(contexts) for source, contexts in contexts_by_source.items()}


# Global source provider instance
_source_provider: Optional[SourceProvider] = None


def get_source_provider() -> SourceProvider:
    """Get global SourceProvider instance (singleton)."""
    global _source_provider
    if _source_provider is None:
        _source_provider = SourceProvider()
    return _source_provider
