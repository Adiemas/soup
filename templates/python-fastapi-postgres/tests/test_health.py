"""Health endpoint test — DB pool stubbed to avoid needing a live Postgres."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


class _StubDB:
    """Stub Database; `ping()` returns True."""

    async def ping(self) -> bool:
        return True

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Build a TestClient with Database.from_env returning the stub."""
    from app import db as db_mod
    from app import main as main_mod

    monkeypatch.setattr(db_mod.Database, "from_env", classmethod(lambda cls: _StubDB()))
    with TestClient(main_mod.app) as c:
        yield c


def test_root(client: Any) -> None:
    """Root endpoint returns service identity."""
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "your-api"


def test_health_ok(client: Any) -> None:
    """Health reports ok when DB pings."""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] is True
