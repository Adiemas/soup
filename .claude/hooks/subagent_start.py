#!/usr/bin/env python
"""SubagentStart hook: inject stack hint + global rules + compliance rules + RAG.

- Stack hint comes from env `SOUP_SUBAGENT_STACK` if set; otherwise inferred
  from `files_allowed` glob in the payload (if any) or left blank.
- Global rules (`rules/global/*.md`) are ALWAYS injected — every subagent
  sees the baseline.
- Compliance rules are injected based on `.soup/intake/active.yaml`'s
  `compliance_flags[]`. Each flag maps to `rules/compliance/<flag>.md`.
  Fail soft: if the intake yaml is absent or malformed, skip compliance
  injection silently.
- If `SOUP_RAG_QUERIES` is set (comma-separated), call `rag/search.py` per
  query and inject a truncated summary. Silent on failure.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


STACK_HINTS: dict[str, tuple[str, str]] = {
    "python": ("python", "Python / FastAPI / pytest / ruff / mypy"),
    "dotnet": ("dotnet", "C# / .NET 8 / xUnit / EF Core"),
    "react": ("react", "React / TypeScript / Vite / RTL / Playwright"),
    "typescript": ("typescript", "TypeScript (strict) / zod at boundaries"),
    "postgres": ("postgres", "PostgreSQL 16 / sqlc / Alembic / EF migrations"),
}

STACK_EXT_HINT: list[tuple[str, str]] = [
    (".py", "python"),
    (".cs", "dotnet"),
    (".csproj", "dotnet"),
    (".tsx", "react"),
    (".jsx", "react"),
    (".ts", "typescript"),
    (".sql", "postgres"),
]

# Compliance flags that map to a rule file under rules/compliance/.
# `public` and `internal-only` are routing/labelling flags only — they do
# not map to a rules file (no injection).
COMPLIANCE_FLAGS_WITH_RULES: frozenset[str] = frozenset(
    {"lab-data", "pii", "phi", "financial"}
)

MAX_RAG_CHARS = 4_000
MAX_RULE_CHARS = 12_000


def _project_root(cwd: Path) -> Path:
    root = cwd
    for _ in range(6):
        if (root / "CLAUDE.md").exists():
            return root
        if root.parent == root:
            break
        root = root.parent
    return cwd


def _infer_stack_from_payload(payload: dict) -> str | None:
    files_allowed = []
    for key in ("files_allowed", "filesAllowed"):
        v = payload.get(key)
        if isinstance(v, list):
            files_allowed.extend(v)
    # Sometimes nested in agent_input or similar.
    agent_input = payload.get("agent_input") or payload.get("agentInput") or {}
    if isinstance(agent_input, dict):
        for key in ("files_allowed", "filesAllowed"):
            v = agent_input.get(key)
            if isinstance(v, list):
                files_allowed.extend(v)

    hits: dict[str, int] = {}
    for g in files_allowed:
        if not isinstance(g, str):
            continue
        g_low = g.lower()
        for ext, stack in STACK_EXT_HINT:
            if ext in g_low:
                hits[stack] = hits.get(stack, 0) + 1
    if not hits:
        return None
    return max(hits, key=lambda k: hits[k])


def _run_rag(root: Path, query: str) -> str | None:
    script = root / "rag" / "search.py"
    if not script.exists():
        return None
    try:
        proc = subprocess.run(
            [sys.executable, str(script), query],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(root),
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None
    except Exception:
        return None


def _load_global_rules(root: Path) -> str:
    """Load every ``rules/global/*.md`` file concatenated with path markers.

    Always runs; fail-soft returns empty string if the directory is
    missing or unreadable.
    """
    gdir = root / "rules" / "global"
    if not gdir.is_dir():
        return ""
    parts: list[str] = []
    for f in sorted(gdir.glob("*.md")):
        try:
            parts.append(
                f"\n\n<!-- {f.relative_to(root)} -->\n"
                + f.read_text(encoding="utf-8")
            )
        except Exception:
            continue
    body = "".join(parts).strip()
    if len(body) > MAX_RULE_CHARS:
        body = body[:MAX_RULE_CHARS] + "\n...(global rules truncated)"
    return body


def _read_active_intake(root: Path) -> dict | None:
    """Read ``.soup/intake/active.yaml`` if present.

    Uses the local ``yaml`` module when importable; falls back to a tiny
    line scanner for ``compliance_flags:`` so the hook has no hard
    dependency beyond stdlib. Returns ``None`` on any failure.
    """
    path = root / ".soup" / "intake" / "active.yaml"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    # Preferred path: real YAML parse.
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # Fallback: shallow extraction of ``compliance_flags`` only.
    flags: list[str] = []
    in_block = False
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("compliance_flags:"):
            # Inline list: ``compliance_flags: [pii, phi]``
            after = stripped.split(":", 1)[1].strip()
            if after.startswith("[") and after.endswith("]"):
                inner = after[1:-1]
                for part in inner.split(","):
                    part = part.strip().strip("\"'")
                    if part:
                        flags.append(part)
                in_block = False
                continue
            if after in ("", "|", ">"):
                in_block = True
                continue
            # Inline scalar (unexpected) — treat as single flag
            flags.append(after.strip("\"'"))
            in_block = False
            continue
        if in_block:
            if stripped.startswith("- "):
                flags.append(stripped[2:].strip().strip("\"'"))
                continue
            # Non-list line ends the block.
            if stripped and not stripped[0].isspace():
                in_block = False
    return {"compliance_flags": flags} if flags else None


def _load_compliance_rules(root: Path, flags: list[str]) -> str:
    """Load ``rules/compliance/<flag>.md`` for each listed flag."""
    cdir = root / "rules" / "compliance"
    if not cdir.is_dir() or not flags:
        return ""
    parts: list[str] = []
    seen: set[str] = set()
    for flag in flags:
        if not isinstance(flag, str):
            continue
        flag = flag.strip()
        if flag in seen or flag not in COMPLIANCE_FLAGS_WITH_RULES:
            continue
        seen.add(flag)
        f = cdir / f"{flag}.md"
        if not f.exists():
            continue
        try:
            parts.append(
                f"\n\n<!-- {f.relative_to(root)} -->\n"
                + f.read_text(encoding="utf-8")
            )
        except Exception:
            continue
    body = "".join(parts).strip()
    if len(body) > MAX_RULE_CHARS:
        body = body[:MAX_RULE_CHARS] + "\n...(compliance rules truncated)"
    return body


def _compliance_flags_from_intake(root: Path) -> list[str]:
    intake = _read_active_intake(root)
    if not isinstance(intake, dict):
        return []
    raw = intake.get("compliance_flags")
    if not isinstance(raw, list):
        return []
    return [f for f in raw if isinstance(f, str)]


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    root = _project_root(cwd)

    stack_env = (os.environ.get("SOUP_SUBAGENT_STACK") or "").strip().lower()
    stack = stack_env if stack_env in STACK_HINTS else (_infer_stack_from_payload(payload) or "")

    parts: list[str] = []
    if stack and stack in STACK_HINTS:
        _, desc = STACK_HINTS[stack]
        parts.append(f"### Stack hint\nAssigned stack: **{stack}** - {desc}")
        parts.append(f"Rules for this stack live at `rules/{stack}/*.md` (auto-injected on Edit/Write).")

    # Always inject rules/global/*.md so every subagent starts with the baseline.
    global_rules = _load_global_rules(root)
    if global_rules:
        parts.append(
            "### Global rules (always injected)\n"
            "Source: `rules/global/*.md`.\n"
            + global_rules
        )

    # Compliance: flag-driven injection from the active intake YAML.
    # Fail soft — if the file is missing (e.g. free-text /specify flow),
    # skip silently without warning.
    flags = _compliance_flags_from_intake(root)
    if flags:
        compliance_rules = _load_compliance_rules(root, flags)
        if compliance_rules:
            applied = [
                f for f in flags if f in COMPLIANCE_FLAGS_WITH_RULES
            ]
            parts.append(
                "### Compliance rules (intake-driven)\n"
                f"Source: `.soup/intake/active.yaml` → flags "
                f"`{', '.join(sorted(set(applied)))}` → "
                f"`rules/compliance/<flag>.md`.\n"
                + compliance_rules
            )

    rag_env = (os.environ.get("SOUP_RAG_QUERIES") or "").strip()
    if rag_env:
        queries = [q.strip() for q in rag_env.split(",") if q.strip()]
        if queries:
            rag_parts: list[str] = ["### RAG context (auto-fetched)"]
            total = 0
            for q in queries:
                res = _run_rag(root, q)
                if not res:
                    rag_parts.append(f"- query `{q}` -> (no results or RAG unavailable)")
                    continue
                snippet = res.strip()
                remaining = MAX_RAG_CHARS - total
                if remaining <= 0:
                    rag_parts.append("...(rag context truncated)")
                    break
                if len(snippet) > remaining:
                    snippet = snippet[:remaining] + "...(truncated)"
                total += len(snippet)
                rag_parts.append(f"**Query:** `{q}`\n\n{snippet}\n")
            parts.append("\n".join(rag_parts))

    additional = "\n\n".join(parts).strip()
    out = {
        "hookSpecificOutput": {
            "hookEventName": "SubagentStart",
            "additionalContext": additional,
        }
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stdout.write(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": ""}}
            )
        )
        sys.exit(0)
