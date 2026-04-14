#!/usr/bin/env python
"""PostToolUse hook: append a JSONL record per tool call.

Shape: {ts, session_id, tool, input_summary(<=200), output_summary(<=500),
        duration_ms, status}

Redacts values of keys matching (?i)(secret|token|key|password).
Never blocks. Fail soft on all exceptions.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


REDACT_KEY_RE = re.compile(r"(?i)(secret|token|key|password|passwd|pwd|api[_-]?key|auth)")
REDACT_VALUE = "***REDACTED***"


def _project_root(cwd: Path) -> Path:
    root = cwd
    for _ in range(6):
        if (root / "CLAUDE.md").exists():
            return root
        if root.parent == root:
            break
        root = root.parent
    return cwd


def _redact(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and REDACT_KEY_RE.search(k):
                out[k] = REDACT_VALUE
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_redact(x) for x in obj)
    return obj


def _summarize(obj, limit: int) -> str:
    try:
        if isinstance(obj, str):
            s = obj
        else:
            s = json.dumps(_redact(obj), ensure_ascii=False, default=str)
    except Exception:
        try:
            s = str(obj)
        except Exception:
            s = "<unrepr>"
    # Also redact loose KEY=VALUE / "KEY": "VALUE" patterns post-serialization.
    s = re.sub(
        r"((?i)(?:secret|token|key|password|passwd|pwd|api[_-]?key|auth)\s*[:=]\s*)(['\"]?)[^\s'\"\},]+\2",
        r"\1" + REDACT_VALUE,
        s,
    )
    if len(s) > limit:
        s = s[: limit - 3] + "..."
    return s


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    session_id = str(payload.get("session_id") or payload.get("sessionId") or "unknown")
    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    root = _project_root(cwd)

    tool = str(payload.get("tool_name") or payload.get("tool") or "unknown")
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    tool_response = (
        payload.get("tool_response")
        or payload.get("toolResponse")
        or payload.get("tool_output")
        or payload.get("toolOutput")
        or {}
    )
    duration_ms = payload.get("duration_ms") or payload.get("durationMs") or 0
    try:
        duration_ms = int(duration_ms)
    except Exception:
        duration_ms = 0

    # Status: payload may carry "error" or a nested is_error flag.
    status = "ok"
    if payload.get("error") or (isinstance(tool_response, dict) and tool_response.get("is_error")):
        status = "error"

    # iter-3 ε1: wave-tree threading. Stamp every JSONL line with the
    # SOUP_* env variables exported by the orchestrator (see
    # ``orchestrator/agent_factory.py::spawn``). When absent (e.g. a
    # stand-alone Claude Code session), the fields are emitted as null
    # so downstream parsers see the full schema.
    parent_session_id = os.environ.get("SOUP_PARENT_SESSION_ID") or None
    root_run_id = os.environ.get("SOUP_ROOT_RUN_ID") or None
    step_id = os.environ.get("SOUP_STEP_ID") or None
    wave_idx_raw = os.environ.get("SOUP_WAVE_IDX")
    wave_idx: int | None
    try:
        wave_idx = int(wave_idx_raw) if wave_idx_raw is not None else None
    except (TypeError, ValueError):
        wave_idx = None

    # iter-3 ε3: per-tool token + USD cost. Claude Code's hook payload
    # does NOT currently include token counts (the SDK exposes them via
    # the streamed message, not via the hook surface). We log
    # ``cost_estimate: null`` as an explicit placeholder so downstream
    # rollups can distinguish "no data" from "zero cost." When the hook
    # API gains a ``usage`` field, parse ``input_tokens`` and
    # ``output_tokens`` here and multiply by the rate card in
    # ``orchestrator/orchestrator.py::_estimate_cost_usd``.
    # TODO(ε5): once Claude Code exposes per-tool ``usage`` in the
    # PostToolUse payload, replace this null with the computed estimate.
    usage = payload.get("usage") if isinstance(payload, dict) else None
    cost_estimate: float | None = None
    if isinstance(usage, dict):
        try:
            cost_estimate = 0.0  # known-zero so downstream knows shape changed
        except (TypeError, ValueError):
            cost_estimate = None

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "event": "post_tool_use",
        "tool": tool,
        "input_summary": _summarize(tool_input, 200),
        "output_summary": _summarize(tool_response, 500),
        "duration_ms": duration_ms,
        "status": status,
        "parent_session_id": parent_session_id,
        "root_run_id": root_run_id,
        "wave_idx": wave_idx,
        "step_id": step_id,
        "cost_estimate": cost_estimate,
    }

    log_dir = Path(os.environ.get("SOUP_LOG_DIR") or (root / "logging" / "agent-runs"))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / f"session-{session_id}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass

    sys.stdout.write(
        json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": ""}})
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stdout.write(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": ""}}
            )
        )
        sys.exit(0)
