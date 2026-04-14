---
description: Ad-hoc no-planning path for trivial changes (single file, <=20 lines). Still enforces TDD iron law and Stop-hook QA gate.
argument-hint: "<ask> [--no-test]"
---

# /quick

## Purpose
Fast path for changes too small to warrant `/specify -> /plan -> /tasks -> /implement`. Bounded. Anything bigger bounces back to the full flow.

`/quick` still honors TDD: a failing test or characterization test is written FIRST, then the code change makes it pass.

## Variables
- `$ARGUMENTS` — free-text ask; required. May end with `--no-test` (see below).

## Agent chain (strict sequence)

`/quick` spawns exactly two subagents, in order, via the `Agent` tool:

1. **`test-engineer`** (sonnet) — writes a single failing test (or a characterization test when the change is a refactor). Its `files_allowed` is narrowed to `tests/**` plus whatever test-fixture files the ask implies. Its `verify_cmd` MUST exit non-zero (red).
2. **`implementer`** (sonnet) — receives the failing-test summary and makes it pass. `files_allowed` covers exactly one existing production file unless the ask clearly needs one new file; hard cap <=20 lines of diff in the production file. Its `verify_cmd` reruns the test and MUST exit zero (green).

Neither step may be skipped.

## Workflow

1. Parse `$ARGUMENTS`. If the ask is empty, abort with a usage message.
2. If the trailing flag `--no-test` is present, REJECT with:
   `{ "status": "rejected", "reason": "TDD iron law; use /quick-yolo only for genuinely untestable trivial changes like typos and formatting." }`
   (`/quick-yolo` is intentionally NOT implemented. Document first, then propose.)
3. Dispatch `test-engineer` with a strict prompt:
   - Write ONE failing test that captures the desired behavior.
   - `files_allowed: ["tests/**"]` (plus fixture paths if needed).
   - `verify_cmd` runs the new test and asserts exit != 0 (e.g. `! pytest tests/test_<x>.py::<case>`).
4. Dispatch `implementer` once step 3 passes (red confirmed):
   - Pass the failing-test path, the assertion that failed, and the spec-intent line from `$ARGUMENTS`.
   - `files_allowed`: exactly one existing file unless ask requires one new file.
   - Hard cap <=20 lines changed in the production file.
   - `verify_cmd`: rerun the test; exit 0 required (green).
5. If either step's scope bounds are exceeded, the subagent MUST abort and emit:
   `{ "status": "bounce", "reason": "...", "recommend": "/plan" }`.
6. On success: Stop hook triggers QA gate (unchanged).

## Output
- Failing-test path + assertion that first failed.
- Diff summary of the production change.
- Verify result (red -> green).
- QAReport verdict.

## Notes
- Do not use `/quick` to "just try something" and iterate — each failed attempt still bills the QA gate.
- Hard refusals: schema migrations, auth code, cross-cutting refactors, anything touching `.claude/` or `CONSTITUTION.md`.
- The `--no-test` flag is intentionally a rejection path, not an escape hatch. If a genuine use case emerges (e.g. a wave of typo fixes), raise it against `/specify` first; do NOT add `/quick-yolo` without that discussion.
