#!/usr/bin/env python
"""SessionStart hook: load .env, validate required vars, emit project overview.

Fail-soft: if anything goes wrong, emit empty additionalContext and do not crash.
Logs the session startup as the first JSONL record for this session.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_ENV_VARS = [
    # Advisory only — missing vars are warned about, not enforced.
    "ANTHROPIC_API_KEY",
]


def _load_dotenv(root: Path) -> dict[str, str]:
    """Load .env using python-dotenv if available, else stdlib fallback."""
    env_path = root / ".env"
    loaded: dict[str, str] = {}
    if not env_path.exists():
        return loaded
    try:
        from dotenv import dotenv_values  # type: ignore

        loaded = {k: v for k, v in dotenv_values(env_path).items() if v is not None}
        for k, v in loaded.items():
            os.environ.setdefault(k, v)
        return loaded
    except Exception:
        # stdlib fallback: KEY=VALUE, ignore blank/# lines.
        try:
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                loaded[k] = v
                os.environ.setdefault(k, v)
        except Exception:
            pass
        return loaded


_RUNBOOK_LIST_CAP = 6


def _list_runbook_titles(root: Path) -> list[str]:
    """Return a capped, alphabetically sorted list of runbook titles.

    Each runbook is ``docs/runbooks/<slug>.md``; the "title" is the first
    ``# heading`` line if present, else the filename stem. Capped at
    ``_RUNBOOK_LIST_CAP`` to avoid context bloat — the full set lives
    in the directory for the operator to browse.
    """
    rb_dir = root / "docs" / "runbooks"
    if not rb_dir.is_dir():
        return []
    titles: list[str] = []
    for p in sorted(rb_dir.glob("*.md")):
        if p.name.lower() == "readme.md":
            continue
        title = p.stem
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("# ") and len(stripped) > 2:
                    title = stripped[2:].strip()
                    break
        except OSError:
            pass
        titles.append(title)
        if len(titles) >= _RUNBOOK_LIST_CAP:
            break
    return titles


def _project_overview(root: Path) -> str:
    parts = [
        "# Soup Framework Session",
        "",
        "You are operating inside the **Soup** agentic Claude Code framework for Streck internal apps.",
        "Non-negotiables (see CLAUDE.md + CONSTITUTION.md):",
        "- TDD is mandatory for production code (red -> green -> refactor).",
        "- No implementation without a written plan for non-trivial work. Use `/specify -> /plan -> /tasks -> /implement`.",
        "- Fresh subagent per substantive task via the orchestrator. Never span >10 turns inline.",
        "- Evidence before claims. Run verify_cmd, read output, cite it.",
        "- Cite RAG retrievals as `[source:path#span]`.",
        "",
        "Stack preference: Python (FastAPI/Typer) > C#/.NET 8 > React+TS > Postgres 16.",
        "Rules are auto-injected by file extension on every Edit/Write.",
    ]
    runbooks = _list_runbook_titles(root)
    if runbooks:
        parts.append("")
        parts.append(
            "Runbooks available in `docs/runbooks/`: "
            + ", ".join(runbooks)
            + ". If Claude hits a known failure, check there first."
        )
    return "\n".join(parts)


def _append_jsonl(log_dir: Path, session_id: str, record: dict) -> None:
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"session-{session_id}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main() -> int:
    started = time.time()
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    session_id = str(payload.get("session_id") or payload.get("sessionId") or "unknown")
    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()

    # Walk up to find project root (where CLAUDE.md lives).
    root = cwd
    for _ in range(6):
        if (root / "CLAUDE.md").exists():
            break
        if root.parent == root:
            break
        root = root.parent

    loaded = _load_dotenv(root)
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]

    overview = _project_overview(root)
    if missing:
        overview += f"\n\n> NOTE: missing env vars (advisory): {', '.join(missing)}"
    if loaded:
        overview += f"\n> Loaded {len(loaded)} var(s) from .env."

    log_dir = Path(os.environ.get("SOUP_LOG_DIR") or (root / "logging" / "agent-runs"))
    _append_jsonl(
        log_dir,
        session_id,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event": "session_start",
            "cwd": str(cwd),
            "root": str(root),
            "dotenv_loaded": len(loaded),
            "missing_env": missing,
            "duration_ms": int((time.time() - started) * 1000),
        },
    )

    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": overview,
        }
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail soft: never block the session.
        sys.stdout.write(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ""}}
            )
        )
        sys.exit(0)
