"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI

from app.db import Database, get_db
from app.models import HealthResponse


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


@app.get("/health", response_model=HealthResponse)
async def health(db: Database = Depends(get_db)) -> HealthResponse:
    """Liveness + DB round-trip check."""
    db_ok = await db.ping()
    return HealthResponse(status="ok" if db_ok else "degraded", db=db_ok)


@app.get("/")
async def root() -> dict[str, Any]:
    """Root greeting."""
    return {"service": "your-api", "version": "0.1.0"}
