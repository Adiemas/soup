"""FastAPI application entry point.

Ships with the soup observability triple out of the box:

* ``/health`` — liveness (process responds).
* ``/ready``  — readiness (DB reachable).
* ``/version`` — build identity (git SHA + build time + env).

A correlation-id middleware reads ``X-Request-Id`` on every request
(generating a UUID4 when absent), binds it into the structlog
contextvars store if structlog is installed, and mirrors it back on
the response. When structlog is not available the stdlib ``logging``
module is used — the middleware keeps the header behaviour either
way.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Request

from app.db import Database, get_db
from app.models import HealthResponse

# Structured logging: prefer structlog when installed (renders JSON in
# prod, human-friendly in dev); otherwise fall back to stdlib logging
# with a best-effort key=value format. Either way, call sites use
# ``log.info("Event.Name_completed", key=value)``-shaped events.
try:  # pragma: no cover - exercised only when structlog is installed
    import structlog

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
            if os.environ.get("APP_ENV", "dev") != "dev"
            else structlog.dev.ConsoleRenderer(),
        ]
    )
    log = structlog.get_logger()
    _STRUCTLOG = True
except ImportError:  # pragma: no cover - exercised when structlog is absent
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("your-api")
    _STRUCTLOG = False


_STARTED_AT = datetime.now(UTC).isoformat()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open/close the shared DB pool."""
    db = Database.from_env()
    await db.open()
    app.state.db = db
    try:
        yield
    finally:
        await db.close()


app = FastAPI(title="your-api", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def correlation_id_mw(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Attach a correlation id to every request + bind it for logging.

    Reads ``X-Request-Id``; generates a UUID4 on miss. Mirrors the id
    on the response. When structlog is present, binds it into
    contextvars so every ``log.info(...)`` inside the request carries
    the id automatically.
    """
    cid = request.headers.get("x-request-id") or uuid.uuid4().hex
    if _STRUCTLOG:
        structlog.contextvars.bind_contextvars(correlation_id=cid)
    try:
        response = await call_next(request)
    finally:
        if _STRUCTLOG:
            structlog.contextvars.clear_contextvars()
    response.headers["x-request-id"] = cid
    return response


@app.get("/health", response_model=HealthResponse)
async def health(db: Database = Depends(get_db)) -> HealthResponse:
    """Liveness + DB round-trip check.

    Kept backward-compatible with the pre-observability template: the
    ``HealthResponse`` shape carries ``status`` + ``db``. Readiness
    lives on ``/ready``.
    """
    db_ok = await db.ping()
    return HealthResponse(status="ok" if db_ok else "degraded", db=db_ok)


@app.get("/ready")
async def ready(db: Database = Depends(get_db)) -> dict[str, Any]:
    """Readiness probe: DB reachable, pool non-degraded.

    Returns 200 with ``status: "ready"`` when deps are up. Returns a
    shape with ``status: "degraded"`` when the DB ping fails — call-
    site can translate to HTTP 503 via a custom response if the
    deployment target (K8s / Vercel) needs it.
    """
    db_ok = await db.ping()
    return {
        "status": "ready" if db_ok else "degraded",
        "checks": {"database": {"ok": db_ok}},
    }


@app.get("/version")
async def version() -> dict[str, Any]:
    """Build identity. No dep calls."""
    return {
        "service": "your-api",
        "git_sha": os.environ.get("GIT_SHA", "dev"),
        "build_time": os.environ.get("BUILD_TIME", _STARTED_AT),
        "env": os.environ.get("APP_ENV", "dev"),
    }


@app.get("/")
async def root() -> dict[str, Any]:
    """Root greeting."""
    return {"service": "your-api", "version": "0.1.0"}
