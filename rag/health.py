"""Quick RAG health check — Postgres, OpenAI key, lightrag-hku.

Invoked via ``just rag-health`` / ``python -m rag.health``. Exits 0 if
everything needed for a RAG ingest is in place, non-zero otherwise.
Output is human-readable (stdout) with a structured JSON trailer
(stderr-friendly for CI).

Checks:
  1. ``OPENAI_API_KEY`` set (required by default ``openai_embed``).
  2. ``lightrag-hku`` importable.
  3. Postgres reachable (via ``POSTGRES_URL`` / ``DATABASE_URL`` or
     the ``POSTGRES_HOST/PORT/USER/PASSWORD/DB`` set from env).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def _check_openai_key() -> tuple[bool, str]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return False, (
            "OPENAI_API_KEY is not set — LightRAG's default openai_embed "
            "will fail on first embed call. Set it in .env or swap "
            "LightRagClient.embedding_func."
        )
    return True, f"OPENAI_API_KEY set ({len(key)} chars)"


def _check_lightrag() -> tuple[bool, str]:
    try:
        import lightrag  # type: ignore[import-not-found]  # noqa: F401
    except Exception as exc:
        return False, f"lightrag-hku not importable: {exc}"
    return True, "lightrag-hku importable"


def _check_postgres() -> tuple[bool, str]:
    url = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL")
    host = os.environ.get("POSTGRES_HOST")
    if not url and not host:
        return False, (
            "Neither POSTGRES_URL / DATABASE_URL nor POSTGRES_HOST is set. "
            "RAG ingest/search requires a pgvector-enabled Postgres."
        )
    # Prefer url-based check via asyncpg if available; else fall back to
    # a raw socket probe on the host/port so we don't force the dep.
    if url:
        return _probe_dsn(url)
    port = int(os.environ.get("POSTGRES_PORT") or 5432)
    return _probe_socket(host or "localhost", port)


def _probe_dsn(dsn: str) -> tuple[bool, str]:
    try:
        import asyncio

        import asyncpg  # type: ignore[import-not-found]
    except Exception:
        # Fall back to socket check if asyncpg unavailable.
        from urllib.parse import urlparse

        parsed = urlparse(dsn)
        return _probe_socket(parsed.hostname or "localhost", parsed.port or 5432)

    async def _ping() -> None:
        conn = await asyncpg.connect(dsn=dsn, timeout=3.0)
        try:
            await conn.fetchval("SELECT 1")
        finally:
            await conn.close()

    try:
        asyncio.run(_ping())
    except Exception as exc:
        return False, f"Postgres unreachable ({dsn!r}): {exc}"
    return True, f"Postgres reachable ({dsn!r})"


def _probe_socket(host: str, port: int) -> tuple[bool, str]:
    import socket

    try:
        with socket.create_connection((host, port), timeout=3.0):
            pass
    except Exception as exc:
        return False, f"cannot reach {host}:{port} — {exc}"
    return True, f"{host}:{port} reachable (TCP only — not authenticated)"


def _run_cli() -> int:
    report: dict[str, Any] = {"checks": [], "status": "ok"}
    ok = True
    for name, fn in (
        ("OPENAI_API_KEY", _check_openai_key),
        ("lightrag-hku", _check_lightrag),
        ("postgres", _check_postgres),
    ):
        passed, msg = fn()
        report["checks"].append(
            {"name": name, "ok": passed, "message": msg}
        )
        marker = "OK " if passed else "FAIL"
        sys.stdout.write(f"[{marker}] {name}: {msg}\n")
        ok = ok and passed
    report["status"] = "ok" if ok else "fail"
    sys.stdout.write("\n")
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover — CLI entry
    raise SystemExit(_run_cli())
