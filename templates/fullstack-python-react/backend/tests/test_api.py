"""Backend API tests — /greet (no DB) and /health (DB ping patched)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient for the app."""
    from app.main import app

    return TestClient(app)


def test_greet(client: TestClient) -> None:
    """Greet returns parametric message."""
    r = client.get("/greet/alice")
    assert r.status_code == 200
    assert r.json()["message"] == "hello, alice"


def test_health_reports_degraded_without_db(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a reachable DB the endpoint reports degraded."""
    from app import main

    async def _false() -> bool:
        return False

    monkeypatch.setattr(main, "_db_ping", _false)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["db"] is False
