#!/usr/bin/env python
"""Stop hook.

- Scans the current session's JSONL log for any PostToolUse record that
  touched a production file (Edit/Write/MultiEdit on an allow-listed file).
- If so, emits additionalContext instructing the model to invoke the
  `qa-orchestrator` agent and produce a `QAReport`.
- Always appends a row to ``logging/sessions.tsv`` (iter-3 ε2):
    ts\tsession_id\tfiles_touched\tverdict_placeholder

  Note (ε2): the stop hook used to write into ``experiments.tsv``, which
  the orchestrator also wrote to with a different 9-column schema. The
  two row shapes corrupted any TSV-loading consumer. The hook now owns
  ``sessions.tsv`` exclusively; ``experiments.tsv`` is orchestrator-only.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


PRODUCTION_EXT_RE = re.compile(r"\.(py|cs|csproj|tsx?|jsx?|sql|sln|toml|json|ya?ml|md)$", re.I)
WRITE_TOOLS = {"Edit", "Write", "MultiEdit"}

# iter-3 ε2: header carries a schema version comment so consumers can
# detect drift between soup releases.
TSV_HEADER = (
    "# soup-schema:sessions-v1\n"
    "ts\tsession_id\tfiles_touched\tverdict_placeholder\n"
)


def _project_root(cwd: Path) -> Path:
    root = cwd
    for _ in range(6):
        if (root / "CLAUDE.md").exists():
            return root
        if root.parent == root:
            break
        root = root.parent
    return cwd


def _scan_touched(log_path: Path) -> list[str]:
    """Return unique file paths touched by Edit/Write/MultiEdit in this session."""
    touched: list[str] = []
    if not log_path.exists():
        return touched
    seen: set[str] = set()
    try:
        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("tool") not in WRITE_TOOLS:
                    continue
                summary = rec.get("input_summary") or ""
                if not isinstance(summary, str):
                    continue
                # Extract file_path values from the JSON-ish summary.
                for m in re.finditer(r'"file_path"\s*:\s*"([^"]+)"', summary):
                    p = m.group(1)
                    if p in seen:
                        continue
                    if PRODUCTION_EXT_RE.search(p):
                        seen.add(p)
                        touched.append(p)
    except Exception:
        pass
    return touched


def _append_tsv(tsv: Path, row: list[str]) -> None:
    try:
        tsv.parent.mkdir(parents=True, exist_ok=True)
        new = not tsv.exists()
        with tsv.open("a", encoding="utf-8") as fh:
            if new:
                fh.write(TSV_HEADER)
            fh.write("\t".join(row) + "\n")
    except Exception:
        pass


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    session_id = str(payload.get("session_id") or payload.get("sessionId") or "unknown")
    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    root = _project_root(cwd)

    log_dir = Path(os.environ.get("SOUP_LOG_DIR") or (root / "logging" / "agent-runs"))
    log_path = log_dir / f"session-{session_id}.jsonl"

    touched = _scan_touched(log_path)
    ts = datetime.now(timezone.utc).isoformat()

    # iter-3 ε2: stop hook owns ``sessions.tsv`` (4 cols).
    # ``experiments.tsv`` is orchestrator-only (9 cols). Writing both
    # shapes into the same file corrupted TSV consumers — keep them
    # split. See ``docs/ARCHITECTURE.md §7``.
    verdict_placeholder = "PENDING_QA" if touched else "NO_EDITS"
    _append_tsv(
        root / "logging" / "sessions.tsv",
        [ts, session_id, ";".join(touched) or "-", verdict_placeholder],
    )

    if not touched:
        out = {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": ""}}
        sys.stdout.write(json.dumps(out))
        return 0

    preview = ", ".join(touched[:10])
    if len(touched) > 10:
        preview += f", ...(+{len(touched) - 10} more)"

    body = (
        "### QA gate required\n"
        "This session modified production files. Before claiming completion you MUST:\n\n"
        "1. Invoke the `qa-orchestrator` subagent (it dispatches `code-reviewer`, "
        "`security-scanner`, and `verifier` in parallel).\n"
        "2. Synthesize a `QAReport` (see `schemas/qa_report.py`) with a verdict of "
        "`APPROVE | NEEDS_ATTENTION | BLOCK`.\n"
        "3. If verdict is not `APPROVE`, dispatch the `verifier` agent (fix-cycle role) "
        "with systematic-debugging context and re-run QA.\n\n"
        f"Files touched ({len(touched)}): {preview}\n"
    )
    out = {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": body}}
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stdout.write(
            json.dumps({"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": ""}})
        )
        sys.exit(0)
