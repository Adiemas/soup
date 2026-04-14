"""psql-wrap — agent-callable Postgres wrapper.

Subcommands:

- ``query <sql> [--allow-write] [--allow-multi]`` — run SQL and stream
  rows as JSON / NDJSON. Read-only by default; every write/DDL path is
  rejected unless ``--allow-write`` is set. Multi-statement input is
  rejected unless ``--allow-multi`` is set.
- ``query-p --sql "... %s ..." --param <v> [...] [--allow-write]`` —
  **canonical safe path** for agent-composed queries. Uses psycopg
  parameter binding; no string concatenation into SQL is possible here.
- ``migrate-up [--dir migrations/]`` — apply forward migrations. The
  bookkeeping table must exist first — run ``migrations-init`` once per
  fresh database. Runtime code never issues DDL for the bookkeeping
  table (Constitution Art. V).
- ``migrate-down [--dir migrations/]`` — revert last migration.
- ``migrations-init`` — create the ``schema_migrations`` bookkeeping
  table. Operator-run, explicit. Idempotent.
- ``schema`` — dump tables/columns.

Connection via env: ``POSTGRES_HOST``, ``POSTGRES_PORT``,
``POSTGRES_DB``, ``POSTGRES_USER``, ``POSTGRES_PASSWORD``
(or ``POSTGRES_DSN``).

Security notes
--------------
The write guard is defense-in-depth, not a substitute for an SQL parser.
It combines:

1. Comment stripping (``--`` to EOL and ``/* ... */`` block comments,
   with quoted strings left intact).
2. Per-statement scanning after splitting on ``;`` (respecting quoted
   strings and dollar-quoted blocks).
3. Keyword match on DML/DDL verbs.
4. Explicit rejection of side-effecting server-side functions
   (``pg_write_file``, ``dblink_exec``, ``COPY ... FROM PROGRAM``, etc.)
   and of ``DO $$ ... $$`` anonymous code blocks.
5. Multi-statement rejection unless ``--allow-multi`` is set.

None of this replaces parameterization. Callers that compose SQL from
user input MUST use ``query-p`` (see Constitution Art. V, security
rule 1.3).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import click

from . import emit_error, emit_ok

# ---------------------------------------------------------------------------
# Write-guard heuristics. See module docstring for the full layered design.

_DML_DDL_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "TRUNCATE",
    "CREATE",
    "DROP",
    "ALTER",
    "GRANT",
    "REVOKE",
    "COMMENT",
    "COPY",
    "REINDEX",
    "VACUUM",
    "CLUSTER",
    "REFRESH",
    "IMPORT",
    "SECURITY",
    "LOCK",
    "CALL",
    "EXECUTE",
)

_WRITE_RE = re.compile(
    r"\b(" + "|".join(_DML_DDL_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# Server-side side-effecting functions and constructs we refuse outright,
# even inside what looks like a SELECT, because they can mutate files or
# run shell/procedural code.
_FORBIDDEN_RE = re.compile(
    r"\b("
    r"pg_write_file"
    r"|pg_read_file"
    r"|pg_read_server_files"
    r"|pg_write_server_files"
    r"|pg_execute_server_program"
    r"|dblink_exec"
    r"|dblink"
    r"|lo_import"
    r"|lo_export"
    r"|copy_from_program"
    r"|system"
    r")\s*\(",
    re.IGNORECASE,
)

# DO $$ ... $$ anonymous code blocks: procedural writes disguised as
# expressions, dynamic SQL via EXECUTE, etc.
_DO_BLOCK_RE = re.compile(
    r"\bDO\s+(?:LANGUAGE\s+\w+\s+)?\$",
    re.IGNORECASE,
)

# COPY ... FROM PROGRAM / TO PROGRAM — shell execution via Postgres.
_COPY_PROGRAM_RE = re.compile(
    r"\bCOPY\b.*?\b(?:FROM|TO)\s+PROGRAM\b",
    re.IGNORECASE | re.DOTALL,
)

# CREATE OR REPLACE FUNCTION ... LANGUAGE plpythonX / plperlX / plsh /
# plv8 etc. — arbitrary code execution via untrusted procedural
# languages. Always rejected (callers should define functions via
# migration files authored by `sql-specialist`, not through the
# agent-callable wrapper).
_UNTRUSTED_LANG_RE = re.compile(
    r"\bLANGUAGE\s+(?:plpython\w*|plperl\w*|plsh|plv8|pljava|c)\b",
    re.IGNORECASE,
)


def _strip_comments(sql: str) -> str:
    """Strip SQL comments while preserving contents of quoted strings.

    Handles:

    - single-quoted string literals (``'...'``) including doubled quotes
      (``''``);
    - double-quoted identifiers (``"..."``);
    - dollar-quoted strings (``$tag$...$tag$``) with an optional tag;
    - line comments (``-- ... EOL``);
    - block comments (``/* ... */``), non-recursive (matches Postgres
      behavior: nested block comments are a parser extension we do not
      rely on).
    """
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        two = sql[i : i + 2]
        # Line comment -> skip to newline (inclusive).
        if two == "--":
            nl = sql.find("\n", i + 2)
            if nl == -1:
                break
            out.append(" ")  # replace with whitespace so tokens don't fuse
            i = nl + 1
            out.append("\n")
            continue
        # Block comment -> skip to */.
        if two == "/*":
            end = sql.find("*/", i + 2)
            if end == -1:
                break
            out.append(" ")
            i = end + 2
            continue
        # Single-quoted literal.
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2  # escaped ''
                        continue
                    j += 1
                    break
                j += 1
            out.append(sql[i:j])
            i = j
            continue
        # Double-quoted identifier.
        if ch == '"':
            j = i + 1
            while j < n:
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append(sql[i:j])
            i = j
            continue
        # Dollar-quoted string: $tag$...$tag$.
        if ch == "$":
            m = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$", sql[i:])
            if m:
                tag = m.group(0)
                end = sql.find(tag, i + len(tag))
                if end == -1:
                    # Unterminated — bail and keep remainder as-is.
                    out.append(sql[i:])
                    break
                out.append(sql[i : end + len(tag)])
                i = end + len(tag)
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_statements(sql: str) -> list[str]:
    """Split SQL on ``;`` respecting quoted strings and dollar-quoted blocks.

    Works on **already comment-stripped** input (comments are replaced
    with whitespace by :func:`_strip_comments`).
    """
    stmts: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == ";":
            text = "".join(buf).strip()
            if text:
                stmts.append(text)
            buf = []
            i += 1
            continue
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            buf.append(sql[i:j])
            i = j
            continue
        if ch == '"':
            j = i + 1
            while j < n:
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            buf.append(sql[i:j])
            i = j
            continue
        if ch == "$":
            m = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$", sql[i:])
            if m:
                tag = m.group(0)
                end = sql.find(tag, i + len(tag))
                if end == -1:
                    buf.append(sql[i:])
                    break
                buf.append(sql[i : end + len(tag)])
                i = end + len(tag)
                continue
        buf.append(ch)
        i += 1
    trailing = "".join(buf).strip()
    if trailing:
        stmts.append(trailing)
    return stmts


class _GuardError(ValueError):
    """Raised when the write-guard rejects a statement."""

    def __init__(self, message: str, code: int = 3) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _is_write_statement(stmt: str) -> bool:
    """Return True if a single statement looks like a writer/DDL.

    The input is expected to be one statement, comments already removed.
    """
    return bool(_WRITE_RE.search(stmt))


def _check_forbidden(stmt: str) -> None:
    """Reject constructs that are never safe in the agent-callable path.

    Raises:
        _GuardError: if the statement contains any forbidden construct.
    """
    if _DO_BLOCK_RE.search(stmt):
        raise _GuardError(
            "DO $$ ... $$ anonymous code blocks are not permitted via "
            "psql-wrap; author a migration instead",
        )
    if _COPY_PROGRAM_RE.search(stmt):
        raise _GuardError(
            "COPY ... FROM/TO PROGRAM is not permitted via psql-wrap",
        )
    if _UNTRUSTED_LANG_RE.search(stmt):
        raise _GuardError(
            "CREATE FUNCTION with plpython/plperl/plsh/plv8/c language "
            "is not permitted via psql-wrap",
        )
    if _FORBIDDEN_RE.search(stmt):
        raise _GuardError(
            "statement calls a side-effecting server function "
            "(pg_write_file / dblink / lo_import / ...)",
        )


def _guard_sql(sql: str, *, allow_write: bool, allow_multi: bool) -> list[str]:
    """Run the full layered write-guard over *sql*.

    Returns the list of individual statements (after split + comment
    strip). Raises :class:`_GuardError` on any guard violation.
    """
    stripped = _strip_comments(sql)
    stmts = _split_statements(stripped)
    if not stmts:
        raise _GuardError("empty SQL after stripping comments", code=3)
    if len(stmts) > 1 and not allow_multi:
        raise _GuardError(
            f"multi-statement SQL rejected ({len(stmts)} statements); "
            "re-run with --allow-multi if intended",
            code=3,
        )
    for stmt in stmts:
        _check_forbidden(stmt)
        if _is_write_statement(stmt) and not allow_write:
            raise _GuardError(
                "write statement detected; re-run with --allow-write "
                "if intended",
                code=3,
            )
    return stmts


# Public alias preserved for tests that imported the old name. Returns
# True if *any* statement in the input would be classified as a write.
def _is_write(sql: str) -> bool:
    """Legacy helper: True if any statement in *sql* is a writer.

    Uses the same comment-stripping + statement-splitting pipeline as
    the guard, so it is consistent with :func:`_guard_sql`.
    """
    stripped = _strip_comments(sql)
    for stmt in _split_statements(stripped):
        if _is_write_statement(stmt):
            return True
    return False


# ---------------------------------------------------------------------------
# Connection helpers.


def _dsn_from_env() -> str:
    """Build a libpq DSN from POSTGRES_* env vars, or POSTGRES_DSN."""
    if dsn := os.environ.get("POSTGRES_DSN"):
        return dsn
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "postgres")
    user = os.environ.get("POSTGRES_USER", "postgres")
    pw = os.environ.get("POSTGRES_PASSWORD", "")
    return f"host={host} port={port} dbname={db} user={user} password={pw}"


def _connect(autocommit: bool = False) -> Any:
    """Open a psycopg connection. Defer import so module loads without driver."""
    try:
        import psycopg  # type: ignore[import-untyped]
    except ImportError as e:
        raise RuntimeError(
            "psycopg is not installed; add 'psycopg[binary]' to dependencies"
        ) from e
    conn = psycopg.connect(_dsn_from_env(), autocommit=autocommit)
    return conn


# ---------------------------------------------------------------------------
# CLI entry points.


@click.group(name="psql-wrap", help="JSON-first Postgres wrapper for soup agents.")
def cli() -> None:
    """Root command group."""


@cli.command("query")
@click.argument("sql")
@click.option("--allow-write", is_flag=True, help="Permit INSERT/UPDATE/DELETE/DDL.")
@click.option(
    "--allow-multi",
    is_flag=True,
    help="Permit multiple semicolon-separated statements.",
)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
@click.option(
    "--ndjson",
    is_flag=True,
    help="Stream rows as NDJSON instead of a single doc.",
)
def query_cmd(
    sql: str,
    allow_write: bool,
    allow_multi: bool,
    json_mode: bool,
    ndjson: bool,
) -> None:
    """Execute SQL and return rows.

    Safety: read-only by default; write statements, multi-statement
    queries, and known dangerous constructs are rejected unless the
    corresponding ``--allow-*`` flag is passed (Constitution Art. V).

    For SQL that takes parameters, prefer the ``query-p`` subcommand —
    it uses psycopg parameter binding which is the canonical safe way
    to compose queries that mix code and data.
    """
    try:
        _guard_sql(sql, allow_write=allow_write, allow_multi=allow_multi)
    except _GuardError as e:
        emit_error(e.message, code=e.code, json_mode=json_mode)
        return
    _execute(sql, params=None, json_mode=json_mode, ndjson=ndjson)


@cli.command("query-p")
@click.option(
    "--sql",
    "sql",
    required=True,
    help="SQL template using psycopg %s placeholders.",
)
@click.option(
    "--param",
    "params",
    multiple=True,
    help=(
        "Positional parameter; repeat for each %s placeholder. "
        "Values are passed through psycopg's parameter binding — no "
        "string interpolation into SQL occurs."
    ),
)
@click.option(
    "--allow-write",
    is_flag=True,
    help="Permit INSERT/UPDATE/DELETE/DDL.",
)
@click.option(
    "--allow-multi",
    is_flag=True,
    help="Permit multiple semicolon-separated statements.",
)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
@click.option(
    "--ndjson",
    is_flag=True,
    help="Stream rows as NDJSON instead of a single doc.",
)
def query_p_cmd(
    sql: str,
    params: tuple[str, ...],
    allow_write: bool,
    allow_multi: bool,
    json_mode: bool,
    ndjson: bool,
) -> None:
    """Parameterized query — the canonical safe path for agent-composed SQL.

    Example::

        psql-wrap query-p \\
            --sql "SELECT * FROM t WHERE id = %s AND status = %s" \\
            --param 123 --param active

    The ``--param`` values are bound by the driver, so SQL-injection
    through values is not possible. The static SQL template is still
    passed through the same write-guard as ``query`` (so an agent that
    tries ``--sql "DELETE FROM ..."`` still hits the read-only check).
    """
    try:
        _guard_sql(sql, allow_write=allow_write, allow_multi=allow_multi)
    except _GuardError as e:
        emit_error(e.message, code=e.code, json_mode=json_mode)
        return
    _execute(
        sql,
        params=tuple(params) if params else None,
        json_mode=json_mode,
        ndjson=ndjson,
    )


def _execute(
    sql: str,
    *,
    params: tuple[str, ...] | None,
    json_mode: bool,
    ndjson: bool,
) -> None:
    """Run guarded SQL and emit rows. Factored out so query / query-p share."""
    try:
        conn = _connect(autocommit=True)
    except Exception as e:  # noqa: BLE001
        emit_error(f"connect failed: {e}", code=2, json_mode=json_mode)
        return
    try:
        with conn.cursor() as cur:
            if params is not None:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            cols = [d.name for d in (cur.description or [])]
            if ndjson:
                wrote = 0
                for row in cur:
                    rec = dict(zip(cols, row, strict=False))
                    sys.stdout.write(
                        json.dumps(rec, default=str, ensure_ascii=False)
                    )
                    sys.stdout.write("\n")
                    wrote += 1
                sys.stdout.flush()
                summary = {"status": "ok", "rows_written": wrote, "columns": cols}
                sys.stdout.write(json.dumps(summary))
                sys.stdout.write("\n")
                return
            rows: list[dict[str, Any]] = [
                dict(zip(cols, r, strict=False)) for r in cur.fetchall()
            ]
        emit_ok(
            {"status": "ok", "rowcount": len(rows), "columns": cols, "rows": rows},
            json_mode=json_mode,
        )
    except Exception as e:  # noqa: BLE001
        emit_error(f"query failed: {e}", code=1, json_mode=json_mode)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Migrations.

# The DDL that creates the bookkeeping table. Exposed as a constant so
# tests and documentation agree. Run via the ``migrations-init``
# subcommand; never called at runtime from inside the wrapper.
MIGRATIONS_INIT_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
""".strip()


def _migrations_dir(path: str) -> Path:
    """Resolve and validate the migrations directory."""
    d = Path(path)
    if not d.is_dir():
        raise RuntimeError(f"migrations dir not found: {d}")
    return d


def _migrations_table_exists(conn: Any) -> bool:
    """Return True if ``schema_migrations`` exists in the current db."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM   information_schema.tables
            WHERE  table_name = 'schema_migrations'
            LIMIT  1
            """
        )
        return cur.fetchone() is not None


def _applied_versions(conn: Any) -> set[str]:
    """Load the set of already-applied migration versions."""
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations")
        return {r[0] for r in cur.fetchall()}


def _discover(dir_: Path, *, suffix: str) -> list[tuple[str, Path]]:
    """List (version, path) tuples for numbered *.sql files."""
    out: list[tuple[str, Path]] = []
    for p in sorted(dir_.glob(f"*.{suffix}")):
        name = p.stem
        ver = name.split("_", 1)[0]
        if not ver.isdigit():
            continue
        out.append((ver, p))
    return out


@cli.command("migrations-init")
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
@click.option(
    "--print-sql",
    is_flag=True,
    help="Print the DDL that would be executed and exit; do not run it.",
)
def migrations_init_cmd(json_mode: bool, print_sql: bool) -> None:
    """Create the ``schema_migrations`` bookkeeping table.

    This is the only path by which the wrapper emits DDL. It is
    operator-run (one-shot, explicit), never called automatically at
    query/migrate-up time. Constitution Art. V forbids runtime DDL in
    runtime code paths.

    The DDL is::

        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

    Idempotent: safe to run against a database that already has the
    table.
    """
    if print_sql:
        sys.stdout.write(MIGRATIONS_INIT_SQL + "\n")
        return
    try:
        conn = _connect(autocommit=False)
    except Exception as e:  # noqa: BLE001
        emit_error(f"connect failed: {e}", code=2, json_mode=json_mode)
        return
    try:
        with conn.cursor() as cur:
            cur.execute(MIGRATIONS_INIT_SQL)
        conn.commit()
        emit_ok(
            {
                "status": "ok",
                "created": True,
                "table": "schema_migrations",
            },
            json_mode=json_mode,
        )
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        emit_error(f"migrations-init failed: {e}", code=1, json_mode=json_mode)
    finally:
        conn.close()


@cli.command("migrate-up")
@click.option("--dir", "dir_", default="migrations", show_default=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def migrate_up_cmd(dir_: str, json_mode: bool) -> None:
    """Apply all pending forward migrations (*.up.sql or *.sql).

    Precondition: ``schema_migrations`` must exist. Run
    ``psql-wrap migrations-init`` once against a fresh database first;
    we do not create the bookkeeping table on the fly.
    """
    try:
        mdir = _migrations_dir(dir_)
        conn = _connect(autocommit=False)
    except Exception as e:  # noqa: BLE001
        emit_error(str(e), code=2, json_mode=json_mode)
        return
    applied: list[str] = []
    try:
        if not _migrations_table_exists(conn):
            emit_error(
                "schema_migrations table missing; run "
                "'psql-wrap migrations-init' first",
                code=5,
                json_mode=json_mode,
            )
            return
        done = _applied_versions(conn)
        candidates = _discover(mdir, suffix="up.sql") or _discover(
            mdir, suffix="sql"
        )
        for ver, path in candidates:
            if ver in done:
                continue
            sql = path.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations(version) VALUES (%s)",
                    (ver,),
                )
            conn.commit()
            applied.append(ver)
        emit_ok(
            {"status": "ok", "applied": applied, "count": len(applied)},
            json_mode=json_mode,
        )
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        emit_error(f"migration failed: {e}", code=1, json_mode=json_mode)
    finally:
        conn.close()


@cli.command("migrate-down")
@click.option("--dir", "dir_", default="migrations", show_default=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def migrate_down_cmd(dir_: str, json_mode: bool) -> None:
    """Revert the most recent migration using its ``*.down.sql`` file.

    Precondition: ``schema_migrations`` must exist (see ``migrations-init``).
    """
    try:
        mdir = _migrations_dir(dir_)
        conn = _connect(autocommit=False)
    except Exception as e:  # noqa: BLE001
        emit_error(str(e), code=2, json_mode=json_mode)
        return
    try:
        if not _migrations_table_exists(conn):
            emit_error(
                "schema_migrations table missing; run "
                "'psql-wrap migrations-init' first",
                code=5,
                json_mode=json_mode,
            )
            return
        with conn.cursor() as cur:
            cur.execute(
                "SELECT version FROM schema_migrations "
                "ORDER BY version DESC LIMIT 1"
            )
            row = cur.fetchone()
        if not row:
            emit_ok(
                {
                    "status": "ok",
                    "reverted": None,
                    "message": "nothing to revert",
                },
                json_mode=json_mode,
            )
            return
        ver = row[0]
        candidates = [
            p for (v, p) in _discover(mdir, suffix="down.sql") if v == ver
        ]
        if not candidates:
            emit_error(
                f"no down migration for version {ver}",
                code=4,
                json_mode=json_mode,
            )
            return
        sql = candidates[0].read_text(encoding="utf-8")
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute("DELETE FROM schema_migrations WHERE version = %s", (ver,))
        conn.commit()
        emit_ok({"status": "ok", "reverted": ver}, json_mode=json_mode)
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        emit_error(f"migrate-down failed: {e}", code=1, json_mode=json_mode)
    finally:
        conn.close()


@cli.command("schema")
@click.option("--schema", "schema_name", default="public", show_default=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def schema_cmd(schema_name: str, json_mode: bool) -> None:
    """Inventory tables + columns for a schema."""
    try:
        conn = _connect(autocommit=True)
    except Exception as e:  # noqa: BLE001
        emit_error(f"connect failed: {e}", code=2, json_mode=json_mode)
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name, column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                (schema_name,),
            )
            rows = cur.fetchall()
        tables: dict[str, list[dict[str, Any]]] = {}
        for t, c, dt, nullable, default in rows:
            tables.setdefault(t, []).append(
                {
                    "column": c,
                    "type": dt,
                    "nullable": nullable == "YES",
                    "default": default,
                }
            )
        emit_ok(
            {"status": "ok", "schema": schema_name, "tables": tables},
            json_mode=json_mode,
        )
    except Exception as e:  # noqa: BLE001
        emit_error(f"schema dump failed: {e}", code=1, json_mode=json_mode)
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    cli()
