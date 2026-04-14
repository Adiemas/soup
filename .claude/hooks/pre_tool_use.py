#!/usr/bin/env python
"""PreToolUse hook for Edit/Write/MultiEdit.

Responsibilities:
1. Enforce `SOUP_FILES_ALLOWED` glob scope (if set). Reject out-of-scope edits
   with `{"decision": "block", "reason": "..."}`.
2. Resolve the stack from the target file extension and inject the matching
   `rules/{stack}/*.md` + `rules/global/*.md` content into additionalContext.

Extension -> stack mapping:
  .py                 -> python
  .cs, .csproj        -> dotnet
  .tsx, .jsx          -> react
  .ts                 -> typescript (only if no .tsx seen this session)
  .sql                -> postgres

Fail soft: on any unexpected error, emit empty additionalContext (do not block).
"""
from __future__ import annotations

import fnmatch
import json
import os
import sys
from pathlib import Path


EXT_STACK: dict[str, str] = {
    ".py": "python",
    ".cs": "dotnet",
    ".csproj": "dotnet",
    ".tsx": "react",
    ".jsx": "react",
    ".ts": "typescript",
    ".sql": "postgres",
}

# Path-pattern routing — runs BEFORE extension-based lookup. First match
# wins. Patterns are fnmatch-style on forward-slash-normalized paths.
# Each entry maps to a rules subdirectory under `rules/`.
PATH_STACK: tuple[tuple[str, str], ...] = (
    # Supabase migrations / config / client modules
    ("**/supabase/**", "supabase"),
    # SQLite state files — rules live under rules/state-persistence/sqlite.md
    # but rules/<stack> is a directory lookup, so we use a dedicated stack
    # folder `state-persistence-sqlite` symlinked logically via file list.
    ("**/*.sqlite", "state-persistence-sqlite"),
    ("**/*.sqlite3", "state-persistence-sqlite"),
    ("**/*.db", "state-persistence-sqlite"),
    # JSON state files under state/ directories
    ("**/state/**/*.json", "state-persistence-json"),
    ("**/.state/**/*.json", "state-persistence-json"),
)

# Virtual stack names -> explicit file lists inside rules/state-persistence/.
# Keeps the pre_tool_use loader simple (it globs rules/<stack>/*.md) while
# allowing a single-directory rule set to be addressable by more than one
# logical stack.
VIRTUAL_STACK_FILES: dict[str, list[str]] = {
    "state-persistence-sqlite": ["rules/state-persistence/sqlite.md"],
    "state-persistence-json": ["rules/state-persistence/json-file.md"],
}

MAX_RULE_CHARS = 12_000  # cap injected context


def _project_root(cwd: Path) -> Path:
    root = cwd
    for _ in range(6):
        if (root / "CLAUDE.md").exists():
            return root
        if root.parent == root:
            break
        root = root.parent
    return cwd


def _extract_file_path(payload: dict) -> str | None:
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    # Edit/Write/MultiEdit all use file_path.
    for key in ("file_path", "filePath", "path"):
        v = tool_input.get(key)
        if isinstance(v, str) and v:
            return v
    # MultiEdit: edits list with per-edit file_path.
    edits = tool_input.get("edits") or []
    if isinstance(edits, list) and edits:
        first = edits[0] or {}
        if isinstance(first, dict):
            v = first.get("file_path") or first.get("filePath") or first.get("path")
            if isinstance(v, str) and v:
                return v
    return None


def _matches_any(path: str, patterns: list[str], root: Path) -> bool:
    p = Path(path)
    rels = [str(p).replace("\\", "/")]
    try:
        rels.append(str(p.resolve().relative_to(root)).replace("\\", "/"))
    except Exception:
        pass
    for pat in patterns:
        pat = pat.strip().replace("\\", "/")
        if not pat:
            continue
        for r in rels:
            if fnmatch.fnmatch(r, pat) or fnmatch.fnmatch(r, f"**/{pat}"):
                return True
    return False


def _stack_for(path: str, seen_tsx: bool) -> str | None:
    p = Path(path)
    name = p.name.lower()
    # Path-pattern routing first — e.g. anything under supabase/ gets the
    # supabase rule pack regardless of extension (.sql, .ts, .toml, etc).
    norm = str(p).replace("\\", "/").lower()
    for pat, stack in PATH_STACK:
        if fnmatch.fnmatch(norm, pat.lower()):
            return stack
    # Longest compound extensions first (e.g. .csproj before .cs... there's no conflict here, but safe).
    for ext, stack in sorted(EXT_STACK.items(), key=lambda kv: -len(kv[0])):
        if name.endswith(ext):
            if ext == ".ts" and seen_tsx:
                return "react"  # treat lone .ts as react-in-project if tsx exists
            return stack
    return None


def _load_rules(root: Path, stack: str) -> str:
    parts: list[str] = []
    # Global first.
    gdir = root / "rules" / "global"
    if gdir.is_dir():
        for f in sorted(gdir.glob("*.md")):
            try:
                parts.append(f"\n\n<!-- {f.relative_to(root)} -->\n" + f.read_text(encoding="utf-8"))
            except Exception:
                continue
    # Virtual stacks (explicit file lists) — used for path-routed rules
    # that share one directory (e.g. rules/state-persistence/).
    if stack in VIRTUAL_STACK_FILES:
        for rel in VIRTUAL_STACK_FILES[stack]:
            f = root / rel
            if f.exists():
                try:
                    parts.append(f"\n\n<!-- {f.relative_to(root)} -->\n" + f.read_text(encoding="utf-8"))
                except Exception:
                    continue
    else:
        # Stack-specific directory: rules/<stack>/*.md
        sdir = root / "rules" / stack
        if sdir.is_dir():
            for f in sorted(sdir.glob("*.md")):
                try:
                    parts.append(f"\n\n<!-- {f.relative_to(root)} -->\n" + f.read_text(encoding="utf-8"))
                except Exception:
                    continue
    body = "".join(parts).strip()
    if len(body) > MAX_RULE_CHARS:
        body = body[:MAX_RULE_CHARS] + "\n...(rules truncated)"
    return body


def _seen_tsx_in_session(session_id: str, root: Path) -> bool:
    """Scan current session JSONL for any .tsx edit/write."""
    try:
        path = root / "logging" / "agent-runs" / f"session-{session_id}.jsonl"
        if not path.exists():
            return False
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if ".tsx" in line:
                    return True
    except Exception:
        return False
    return False


def _block(reason: str) -> int:
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    return 0


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    session_id = str(payload.get("session_id") or payload.get("sessionId") or "unknown")
    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    root = _project_root(cwd)

    file_path = _extract_file_path(payload)
    if not file_path:
        sys.stdout.write(
            json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ""}})
        )
        return 0

    # Enforce SOUP_FILES_ALLOWED.
    allowed = os.environ.get("SOUP_FILES_ALLOWED", "").strip()
    if allowed:
        patterns = [p for p in allowed.split(",") if p.strip()]
        if patterns and not _matches_any(file_path, patterns, root):
            return _block(
                f"Edit rejected: '{file_path}' is outside SOUP_FILES_ALLOWED scope "
                f"({', '.join(patterns)}). Split the task or widen the scope."
            )

    seen_tsx = _seen_tsx_in_session(session_id, root)
    stack = _stack_for(file_path, seen_tsx)
    if not stack:
        sys.stdout.write(
            json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ""}})
        )
        return 0

    rules = _load_rules(root, stack)
    if not rules:
        sys.stdout.write(
            json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ""}})
        )
        return 0

    header = (
        f"### Rules injected for `{Path(file_path).name}` (stack: **{stack}**)\n"
        f"Follow these before writing. They come from `rules/global/*.md` + `rules/{stack}/*.md`.\n"
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": header + rules,
        }
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stdout.write(
            json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ""}})
        )
        sys.exit(0)
