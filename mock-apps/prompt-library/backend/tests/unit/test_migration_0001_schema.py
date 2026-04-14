"""RED-phase test for Alembic migration 0001 (Streck Prompt Library).

Written by ``test-engineer`` under /implement wave 1. Asserts the migration
creates the `prompts` and `prompt_versions` tables per plan T1, plus the
GIN FTS index, and that ``downgrade`` drops them. Fails until
``sql-specialist`` authors ``migrations/versions/0001_initial.py``.

See ``specs/prompt-library-2026-04-14.md`` REQ-1, REQ-2, REQ-7.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

MIGRATIONS_DIR = Path(__file__).parents[2] / "migrations"


@pytest.fixture(scope="module")
def db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Return a URL to an ephemeral Postgres via testcontainers.

    Falls back to the docker-compose test service if testcontainers is
    unavailable (e.g. in constrained CI shells).
    """
    try:
        from testcontainers.postgres import PostgresContainer  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("testcontainers not installed; install test extras")
    pg = PostgresContainer("postgres:16-alpine")
    pg.start()
    yield pg.get_connection_url().replace("postgresql+psycopg2", "postgresql")
    pg.stop()


def _run_alembic(db_url: str, direction: str) -> None:
    from alembic import command  # type: ignore[import-not-found]
    from alembic.config import Config  # type: ignore[import-not-found]

    cfg = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    if direction == "up":
        command.upgrade(cfg, "head")
    else:
        command.downgrade(cfg, "base")


def test_upgrade_creates_prompts_table(db_url: str) -> None:
    """After ``alembic upgrade head`` the ``prompts`` table exists."""
    _run_alembic(db_url, "up")
    engine = create_engine(db_url)
    cols = {c["name"] for c in inspect(engine).get_columns("prompts")}
    assert cols >= {
        "id", "title", "body", "tags", "created_at", "updated_at", "deleted_at",
    }


def test_upgrade_creates_prompt_versions_table(db_url: str) -> None:
    """``prompt_versions`` has FK to prompts and unique (prompt_id, version)."""
    engine = create_engine(db_url)
    fks = inspect(engine).get_foreign_keys("prompt_versions")
    assert any(fk["referred_table"] == "prompts" for fk in fks), (
        "prompt_versions must FK prompts.id"
    )
    uniques = inspect(engine).get_unique_constraints("prompt_versions")
    cols = {tuple(u["column_names"]) for u in uniques}
    assert ("prompt_id", "version") in cols


def test_upgrade_creates_fts_gin_index(db_url: str) -> None:
    """GIN index on ``to_tsvector(title || body)`` exists (REQ-3 <200ms)."""
    engine = create_engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'prompts' AND indexname LIKE '%fts%'"
            )
        ).fetchall()
    assert rows, "expected a *_fts_* index on prompts"
    assert any("gin" in r[0].lower() and "tsvector" in r[0].lower() for r in rows)


def test_downgrade_drops_tables(db_url: str) -> None:
    """``alembic downgrade base`` removes both tables cleanly."""
    _run_alembic(db_url, "down")
    engine = create_engine(db_url)
    tables = set(inspect(engine).get_table_names())
    assert "prompts" not in tables
    assert "prompt_versions" not in tables
