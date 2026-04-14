"""MCP server exposing the Soup RAG tools.

Run via ``python -m rag.mcp_server`` or ``soup rag-mcp`` (see
``orchestrator.cli``). Implements three tools:

  - ``rag_search(query, mode, top_k)``  → list[Retrieval]
  - ``rag_ingest(source_uri)``          → IngestReport
  - ``rag_list_sources()``              → list of currently indexed paths

Uses the ``mcp`` Python SDK (FastMCP style).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from rag.client import LightRagClient, Retrieval, SearchMode
from rag.ingest import Ingester
from rag.search import Searcher

logger = logging.getLogger("soup.rag.mcp_server")

_VALID_MODES: tuple[SearchMode, ...] = ("hybrid", "vector", "graph")


def _build_client() -> LightRagClient:
    working_dir = os.environ.get("SOUP_RAG_WORKDIR", "./.soup/rag_storage")
    provider = os.environ.get("SOUP_RAG_LLM_PROVIDER", "anthropic")
    return LightRagClient.from_env(working_dir=working_dir, llm_provider=provider)


def build_server() -> Any:
    """Construct the FastMCP server and register tools.

    Kept as a function so tests can stub it without importing ``mcp``.
    """
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"mcp SDK unavailable: {exc}") from exc

    mcp = FastMCP("soup-rag")
    client = _build_client()
    searcher = Searcher(client=client)
    ingester = Ingester(client=client)

    @mcp.tool()
    async def rag_search(
        query: str,
        mode: str = "hybrid",
        top_k: int = 8,
    ) -> str:
        """Semantic + graph RAG search over indexed Streck knowledge.

        Returns a JSON array of {content, source_path, span, score, citation}.
        """
        m: SearchMode = mode if mode in _VALID_MODES else "hybrid"  # type: ignore[assignment]
        results: list[Retrieval] = await searcher.search(query, mode=m, top_k=top_k)
        return json.dumps([r.model_dump() for r in results], indent=2)

    @mcp.tool()
    async def rag_ingest(source_uri: str) -> str:
        """Ingest a source into the RAG index.

        URI schemes: ``file://path``, ``github://owner/repo@branch``,
        ``ado://org/project/wiki``, ``https://…``.
        """
        report = await ingester.ingest_uri(source_uri)
        return json.dumps(report.model_dump(), indent=2)

    @mcp.tool()
    async def rag_list_sources() -> str:
        """List the source paths currently present in the RAG index."""
        return json.dumps(await client.list_sources(), indent=2)

    return mcp


def main() -> None:
    """Entrypoint for ``python -m rag.mcp_server``."""
    logging.basicConfig(level=os.environ.get("SOUP_LOG_LEVEL", "INFO"))
    server = build_server()
    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("rag mcp server interrupted")
    except Exception as exc:
        logger.exception("rag mcp server crashed: %s", exc)
        raise


if __name__ == "__main__":
    # Some MCP SDKs require an explicit asyncio runner; FastMCP.run is sync.
    # Keep the fallback for older SDKs.
    try:
        main()
    except TypeError:
        asyncio.run(main())  # type: ignore[arg-type]
