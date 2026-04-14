"""Postgres connection pool using psycopg 3 (async)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from psycopg_pool import AsyncConnectionPool


def _dsn() -> str:
    """Build a libpq DSN from POSTGRES_* env vars."""
    if dsn := os.environ.get("POSTGRES_DSN"):
        return dsn
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "app")
    user = os.environ.get("POSTGRES_USER", "app")
    pw = os.environ.get("POSTGRES_PASSWORD", "app")
    return f"host={host} port={port} dbname={db} user={user} password={pw}"


@dataclass
class Database:
    """Thin wrapper around psycopg_pool.AsyncConnectionPool."""

    pool: AsyncConnectionPool

    @classmethod
    def from_env(cls) -> "Database":
        """Construct a pool from env config. Does not open — call ``open()``."""
        pool = AsyncConnectionPool(conninfo=_dsn(), min_size=1, max_size=10, open=False)
        return cls(pool=pool)

    async def open(self) -> None:
        """Open the pool."""
        await self.pool.open()

    async def close(self) -> None:
        """Close the pool."""
        await self.pool.close()

    async def ping(self) -> bool:
        """Return True if SELECT 1 succeeds."""
        try:
            async with self.pool.connection() as conn, conn.cursor() as cur:
                await cur.execute("SELECT 1")
                row = await cur.fetchone()
                return bool(row and row[0] == 1)
        except Exception:  # noqa: BLE001
            return False

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Run ``sql`` and return list of dicts."""
        async with self.pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, params)
            cols = [d.name for d in (cur.description or [])]
            rows = await cur.fetchall()
        return [dict(zip(cols, r, strict=False)) for r in rows]


def get_db(request: Request) -> Database:
    """FastAPI dependency: pull the shared pool off ``app.state``."""
    return request.app.state.db
