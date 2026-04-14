"""FastAPI entry point for the fullstack backend."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response model for GET /health."""

    status: str
    db: bool


class GreetResponse(BaseModel):
    """Response model for GET /greet/{name}."""

    message: str


async def _db_ping() -> bool:
    """SELECT 1 via psycopg; True on success, False on any failure."""
    try:
        import psycopg  # type: ignore[import-untyped]
    except ImportError:
        return False
    dsn = os.environ.get("POSTGRES_DSN") or (
        f"host={os.environ.get('POSTGRES_HOST', 'db')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')} "
        f"dbname={os.environ.get('POSTGRES_DB', 'app')} "
        f"user={os.environ.get('POSTGRES_USER', 'app')} "
        f"password={os.environ.get('POSTGRES_PASSWORD', 'app')}"
    )
    try:
        async with await psycopg.AsyncConnection.connect(dsn) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                row = await cur.fetchone()
                return bool(row and row[0] == 1)
    except Exception:  # noqa: BLE001
        return False


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """No-op lifespan (placeholder for future pool mgmt)."""
    yield


app = FastAPI(title="fullstack-backend", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness + DB reachability."""
    ok = await _db_ping()
    return HealthResponse(status="ok" if ok else "degraded", db=ok)


@app.get("/greet/{name}", response_model=GreetResponse)
async def greet(name: str) -> GreetResponse:
    """Simple parametric endpoint consumed by the frontend example."""
    safe = name.strip()[:64] or "world"
    return GreetResponse(message=f"hello, {safe}")
