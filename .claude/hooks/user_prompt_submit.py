#!/usr/bin/env python
"""UserPromptSubmit hook: detect intent and suggest a relevant skill.

Never blocks. Emits a short additionalContext hint when it matches a pattern.
"""
from __future__ import annotations

import json
import re
import sys


# Keyword -> (skill name(s), rationale)
INTENT_PATTERNS: list[tuple[re.Pattern[str], list[str], str]] = [
    (
        re.compile(
            r"\b(bug|error|traceback|stack\s*trace|exception|fails?|failing|broken|crash(es|ing)?|regression)\b",
            re.I,
        ),
        ["systematic-debugging"],
        "This looks like a debugging task - use the 4-phase root-cause procedure, no guessing.",
    ),
    (
        re.compile(
            r"\b(feature|build|implement|add\s+(a|the|new)|create\s+(a|an|new)|design|introduce)\b", re.I
        ),
        ["brainstorming", "spec-driven-development"],
        "Creative work - brainstorm first, then run the `/specify -> /plan -> /tasks -> /implement` flow.",
    ),
    (
        re.compile(r"\b(refactor|clean\s*up|restructure|reorganize|modernize)\b", re.I),
        ["brainstorming", "tdd"],
        "Refactor - confirm scope via brainstorming, keep a green test suite throughout.",
    ),
    (
        re.compile(r"\b(test|tests|pytest|xunit|coverage|tdd)\b", re.I),
        ["tdd"],
        "Test-related work - TDD gates apply: RED -> GREEN -> REFACTOR.",
    ),
    (
        re.compile(r"\b(migration|schema|database|postgres|sqlc|alembic)\b", re.I),
        ["spec-driven-development"],
        "DB/schema work - goes through `sql-specialist` with forward+back migrations.",
    ),
    (
        re.compile(r"\b(security|vulnerab|owasp|secret|credential)\b", re.I),
        ["requesting-code-review"],
        "Security-flavored - request a code review and run the security-scanner.",
    ),
    (
        re.compile(r"\b(plan|tasks?|roadmap)\b", re.I),
        ["writing-plans"],
        "Planning work - use the `writing-plans` skill to produce approved, bite-sized tasks.",
    ),
]


def _detect(prompt: str) -> tuple[list[str], list[str]]:
    skills: list[str] = []
    notes: list[str] = []
    for pat, sk, note in INTENT_PATTERNS:
        if pat.search(prompt):
            for s in sk:
                if s not in skills:
                    skills.append(s)
            notes.append(note)
    return skills, notes


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    prompt = str(payload.get("prompt") or payload.get("user_prompt") or "")
    skills, notes = _detect(prompt)

    if not skills:
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ""}}
        sys.stdout.write(json.dumps(out))
        return 0

    lines = ["### Skill suggestions (advisory)"]
    for note in notes:
        lines.append(f"- {note}")
    lines.append("")
    lines.append(f"Candidate skills: `{', '.join(skills)}`")
    lines.append("Invoke via the `Skill` tool; do not self-narrate.")

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(lines),
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
                {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ""}}
            )
        )
        sys.exit(0)
