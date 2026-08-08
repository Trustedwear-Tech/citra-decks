"""
Agentic RAG System for Citra AI Service
===========================================

This package implements an intelligent orchestrator using LangGraph to replace
hardcoded if-else conditions in query processing. It provides autonomous
decision-making for retrieval strategies based on query analysis.

Components:
- QueryOrchestrator: Main LangGraph-based orchestrator
- RetrievalAgents: Specialized agents for different data sources
- StrategyPlanner: Intelligent strategy selection
- ContextMerger: Smart context aggregation and ranking
- ParallelExecutionManager: Optimized parallel execution for performance

Lazy loading (PEP 562): importing this package — or just a lightweight submodule
like ``agentic_rag.circuit_breaker`` — must NOT drag in the heavy orchestrator
dependencies (langgraph, llama_index). Those load only when QueryOrchestrator /
RETRIEVAL_TOOLS / etc. are actually accessed, and still degrade to ``None`` (with
a warning) if the optional dependency is missing — same behaviour as before, just
deferred. Consumers that don't use the orchestrator (e.g. citra-workflow, which
only needs circuit_breaker) pay nothing and emit no warnings.
"""

import logging
from importlib import import_module

__version__ = "1.0.0"

# Public attribute -> (submodule, symbol). Resolved on first access.
_LAZY_ATTRS = {
    "QueryOrchestrator": (".orchestrator", "QueryOrchestrator"),
    "QueryState": (".orchestrator", "QueryState"),
    "QueryIntent": (".orchestrator", "QueryIntent"),
    "RetrievalStrategy": (".orchestrator", "RetrievalStrategy"),
    "SubQuery": (".orchestrator", "SubQuery"),
    "BaseRetrievalAgent": (".agents", "BaseRetrievalAgent"),
    "ContextMerger": (".context_merger", "ContextMerger"),
    "ParallelExecutionManager": (".parallel_executor", "ParallelExecutionManager"),
    "OptimizedRetrievalExecutor": (".parallel_executor", "OptimizedRetrievalExecutor"),
    "RETRIEVAL_TOOLS": (".tools", "RETRIEVAL_TOOLS"),
}

__all__ = list(_LAZY_ATTRS.keys())


def __getattr__(name):
    """Import an orchestrator component on first access (PEP 562).

    If the optional heavy dependency (langgraph / llama_index) is unavailable,
    degrade to ``None`` with a warning — preserving the old eager try/except
    semantics, but only paid by code that actually touches the component.
    """
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    try:
        value = getattr(import_module(module_name, __name__), attr)
    except ImportError as e:
        logging.warning(f"Failed to import {name} from agentic_rag: {e}")
        value = None
    globals()[name] = value  # cache so repeat access is cheap and stable
    return value


def __dir__():
    return sorted(list(globals().keys()) + __all__)
