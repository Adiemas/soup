"""Soup RAG subsystem — LightRAG + Postgres + MCP wrapper.

Exposes the canonical client, datatypes, and module-level sync-bridge
functions (``search``, ``ingest``) used across orchestrator, CLI
wrappers, and the MCP server.

Citation format (canonical): every ``Retrieval`` carries
``citation = "[source:<path>#<span>]"``. The ``source:`` prefix is
load-bearing — downstream validators (CLAUDE.md iron law 6, the
``agentic-rag-research`` skill) grep for the exact prefix. Earlier
iter-2 code emitted ``[<path>#<span>]`` without the prefix; iter-3
canonicalises on ``[source:...]`` everywhere.
"""

from __future__ import annotations

from rag.client import (
    IngestReport,
    LightRagClient,
    RagUnavailable,
    Retrieval,
    SearchMode,
)
from rag.ingest import ingest
from rag.search import search

__all__ = [
    "IngestReport",
    "LightRagClient",
    "RagUnavailable",
    "Retrieval",
    "SearchMode",
    "ingest",
    "search",
]
