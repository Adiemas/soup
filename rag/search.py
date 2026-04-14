"""Searcher — thin wrapper around LightRagClient.search with markdown rendering.

Also exposes a module-level ``search()`` sync-bridge function and a CLI:

    python -m rag.search --query "..." [--mode hybrid] [--top-k 8]

The CLI emits a JSON document to stdout so agents / shell pipelines can parse
the result without touching the Python API.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any

from rag.client import LightRagClient, RagUnavailable, Retrieval, SearchMode


@dataclass
class Searcher:
    """Normalizes citations and renders retrievals as a markdown block."""

    client: LightRagClient

    async def search(
        self,
        query: str,
        *,
        mode: SearchMode = "hybrid",
        top_k: int = 8,
    ) -> list[Retrieval]:
        results = await self.client.search(query, mode=mode, top_k=top_k)
        return [self._ensure_citation(r) for r in results]

    async def search_markdown(
        self,
        query: str,
        *,
        mode: SearchMode = "hybrid",
        top_k: int = 8,
    ) -> str:
        results = await self.search(query, mode=mode, top_k=top_k)
        return self.render_markdown(query, results)

    @staticmethod
    def _ensure_citation(r: Retrieval) -> Retrieval:
        # Canonical citation format: ``[source:<path>#<span>]`` (see
        # ``rag.client.Retrieval`` docstring).
        if r.citation:
            return r
        return r.model_copy(
            update={"citation": f"[source:{r.source_path}#{r.span}]"}
        )

    @staticmethod
    def render_markdown(query: str, results: list[Retrieval]) -> str:
        """Return a markdown-friendly result block with citations."""
        if not results:
            return f"# RAG: {query}\n\n_No results._\n"
        lines = [f"# RAG: {query}", ""]
        for i, r in enumerate(results, 1):
            score = f" (score={r.score:.3f})" if r.score else ""
            lines.append(f"## Result {i}{score} {r.citation}")
            lines.append("")
            lines.append(r.content.strip())
            lines.append("")
        return "\n".join(lines)


# ---------- module-level bridge functions ---------------------------------


async def _search_async(
    query: str,
    *,
    mode: SearchMode = "hybrid",
    top_k: int = 8,
    client: LightRagClient | None = None,
) -> list[Retrieval]:
    """Async implementation shared by sync bridge and CLI."""
    rag_client = client or LightRagClient.from_env()
    searcher = Searcher(client=rag_client)
    try:
        return await searcher.search(query, mode=mode, top_k=top_k)
    finally:
        if client is None:
            await rag_client.close()


def search(
    query: str,
    *,
    mode: SearchMode = "hybrid",
    top_k: int = 8,
) -> list[Retrieval]:
    """Sync bridge over ``Searcher.search``.

    Constructs a ``LightRagClient`` from env (``POSTGRES_URL`` /
    ``DATABASE_URL``), runs the async search on a fresh event loop, and
    returns the normalized ``Retrieval`` rows. Used by ``orchestrator.cli
    search`` and by scripts that cannot manage their own loop.

    Raises:
        RagUnavailable: if the LightRAG backend cannot be reached.
    """
    return asyncio.run(_search_async(query, mode=mode, top_k=top_k))


# ---------- CLI -----------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rag.search",
        description="Query the soup RAG pipeline and emit JSON to stdout.",
    )
    parser.add_argument(
        "--query",
        "-q",
        required=True,
        help="Natural-language query string.",
    )
    parser.add_argument(
        "--mode",
        choices=("hybrid", "vector", "graph"),
        default="hybrid",
        help="LightRAG search mode (default: hybrid).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=8,
        help="Maximum number of hits to return (default: 8).",
    )
    parser.add_argument(
        "--filter",
        default=None,
        help="Optional path-prefix filter (applied client-side).",
    )
    return parser


def _run_cli(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    mode: SearchMode = args.mode
    payload: dict[str, Any]
    try:
        hits = search(args.query, mode=mode, top_k=args.top_k)
    except RagUnavailable as exc:
        payload = {
            "query": args.query,
            "mode": mode,
            "top_k": args.top_k,
            "status": "unavailable",
            "error": str(exc),
            "hits": [],
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 2
    except Exception as exc:  # pragma: no cover — defensive
        payload = {
            "query": args.query,
            "mode": mode,
            "top_k": args.top_k,
            "status": "error",
            "error": repr(exc),
            "hits": [],
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 2

    if args.filter:
        prefix = args.filter
        hits = [h for h in hits if h.source_path.startswith(prefix)]

    payload = {
        "query": args.query,
        "mode": mode,
        "top_k": args.top_k,
        "status": "ok",
        "hits": [h.model_dump() for h in hits],
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    raise SystemExit(_run_cli())
