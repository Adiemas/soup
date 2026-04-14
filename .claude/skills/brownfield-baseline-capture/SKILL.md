---
name: brownfield-baseline-capture
description: Use before the first edit to any existing codebase that has a passing test suite, public API, DB schema, or shipped contract. 4-phase enumerate → capture → modify → diff loop that freezes the "currently working" surface before change and compares after.
---

# Brownfield Baseline Capture

## Overview

Brownfield edits silently regress things the per-step `verify_cmd` never
touches: a neighbouring test module, the OpenAPI shape of an unrelated
endpoint, an enum value a consumer reads. The per-step contract is too
narrow; the plan needs a freeze line drawn across the *whole* "currently
passing" surface, captured once before S1, captured again after the
final step, diffed.

This skill is the procedural gate that puts the freeze in place. It
pairs with the new `ExecutionPlan.regression_baseline_cmd` field
(see `schemas/execution_plan.py`) — the command this skill produces is
what the orchestrator runs pre-wave and post-wave.

## Iron Law

```
FREEZE WHAT'S ALREADY WORKING BEFORE YOU CHANGE IT. DIFF BEFORE YOU SHIP.
```

A plan whose `regression_baseline_cmd` stays `None` on a brownfield
feature is, by default, shipping blind. The per-step `verify_cmd`
catches local breakage; the baseline catches the neighbour it never
saw.

## Process

### Phase 1 — Enumerate

Name the canonical "passing" surface. Write it down before running
anything.

1. **Test suite.** Is there a green baseline today? Run the full
   suite once; record which tests pass, fail, skip. Skipped tests are
   not a baseline — either unskip them as part of this step or mark
   them in the baseline output explicitly.
2. **API contract.** If the repo exposes HTTP, does it have a
   checked-in OpenAPI? If not, generate one **now** and commit it —
   the first brownfield edit without a baseline has no truth to
   regress against.
3. **DB schema.** If the service owns a Postgres schema, capture
   `pg_dump --schema-only` output. DDL drift is an invisible
   brownfield trap.
4. **Endpoint set.** Enumerate the handlers (FastAPI router,
   ASP.NET controllers, Express routes). Additions are fine;
   disappearances are regressions.
5. **Observable behaviours that aren't tested.** Canonical scenario
   outputs, response-body hashes for "frozen" endpoints, migration
   version counts. Record these as hashes — small, diff-friendly.

Output: a **surface manifest** noting which surfaces will be part of
the freeze. A plan that enumerates test-suite only and skips API is
leaving half the truth uncovered.

### Phase 2 — Capture

Produce deterministic artefacts under `.soup/baseline/pre/` (run
locally before handing the plan to the orchestrator, or use
`regression_baseline_cmd` and let the orchestrator write to
`.soup/baseline/<run_id>/pre.txt`).

1. Write the command as a **single line** (the orchestrator runs it
   verbatim). Chain with `&&` only if every piece uses an allowlisted
   executable (`pytest`, `just`, `python`, etc. — see
   `orchestrator/orchestrator.py::_VERIFY_CMD_ALLOWLIST`).
2. Use commands that emit **deterministic output**. `pytest --co -q`
   is deterministic; `pytest -v` embeds wall-clock times. The goal is
   a textual artefact that `diff` can reason about.
3. Prefer **collecting** over **running** where possible — you want
   the identity of passing tests, not the timing. Running the suite
   once at pre-capture is fine and often necessary, but the *artefact*
   should be canonical form.
4. Commit the pre-capture under `.soup/baseline/pre/` so the plan can
   be re-executed from a fresh worktree without re-deriving it. The
   orchestrator only overwrites `pre.txt`/`post.txt` under a per-run
   subdirectory; the checked-in copy is the source of truth for
   audits.

### Phase 3 — Modify

Run the plan. The orchestrator will honour `regression_baseline_cmd`
automatically:

1. Before the first wave: command runs once, output → `pre.txt`.
2. Waves execute. Per-step `verify_cmd` continues to guard per-step
   scope.
3. After the final wave succeeds: command runs once more, output →
   `post.txt`. Skipped on abort — the pre file is preserved for
   post-mortem.

### Phase 4 — Diff

The orchestrator writes the unified diff to `diff.txt`. Any
previously-passing line missing in `post.txt` flags the run as
`regression` (status distinct from `passed`/`failed`/`aborted`). The
QA gate picks this up as a high-severity finding.

1. Read `diff.txt`. Every missing line is a hypothesis: "this test
   used to pass; now it doesn't exist or doesn't pass."
2. For each missing line:
   - If the test was intentionally removed → update the plan spec
     with the rationale, capture a new baseline, re-run.
   - If the test regressed → diagnose via `systematic-debugging` skill.
   - If the line is noise (e.g. timing-sensitive output leaked in) →
     tighten the baseline command; the command is wrong, not the
     code.
3. `APPROVE` requires a clean diff or an explicit operator note on
   every missing line. Don't auto-accept regression as "that's
   expected" without a spec amendment.

## Red flags

| "Just run the tests after" | Reality |
|---|---|
| "The per-step pytest passed, we're good." | That pytest ran `-k` filter on a scoped path. Neighbour tests are untouched, and brownfield breakage lives in the neighbour. |
| "OpenAPI is regenerated by CI, skip it locally." | CI's regen and your local edit diverge silently. Capture the pre-OpenAPI; CI compares apples to apples. |
| "DB schema hasn't changed." | Unless you dumped it, you don't know. Alembic heads can drift, enum values can flip, indices can vanish. |
| "This is a one-line fix." | One-line fixes to shared service code have outsized blast radius — that's the actual brownfield risk. |
| "No baseline exists, so there's nothing to compare against — ship." | Create the baseline now, commit it, re-run. A first-edit without a baseline is a non-starter for any brownfield flow. |
| "The baseline cmd is slow; I'll skip it for quick edits." | Use `/quick` for edits that don't need the baseline. If an edit warrants a full ExecutionPlan, it warrants the baseline. |
| "I'll just read the diff later if something breaks." | "Later" is after merge. Diff is a pre-merge gate, not a post-mortem input. |

## Example `regression_baseline_cmd` snippets

**Python / pytest** — collect test IDs into a deterministic text file:

```bash
pytest --co -q > .soup/baseline/pre/tests.txt
```

**Python + FastAPI OpenAPI dump** — combine with the test collect:

```bash
pytest --co -q > .soup/baseline/pre/tests.txt && python -m app.main --print-openapi > .soup/baseline/pre/openapi.json
```

**.NET / xUnit** — list tests via `dotnet test --list-tests`:

```bash
dotnet test --list-tests --nologo > .soup/baseline/pre/tests.txt
```

**OpenAPI hash only** (already running service):

```bash
python cli_wrappers/openapi_snapshot.py > .soup/baseline/pre/openapi.json
```

**Postgres schema dump** (DB-owning service):

```bash
just db-schema-dump > .soup/baseline/pre/schema.sql
```

**React / vitest** — list tests without running them:

```bash
npx vitest list > .soup/baseline/pre/tests.txt
```

**Combined full-surface freeze**:

```bash
pytest --co -q > .soup/baseline/pre/tests.txt && just db-schema-dump > .soup/baseline/pre/schema.sql && python cli_wrappers/openapi_snapshot.py > .soup/baseline/pre/openapi.json
```

All of the above use executables on the orchestrator's `verify_cmd`
allowlist — the field validator on `ExecutionPlan` rejects commands
using anything else before the plan ever reaches the orchestrator.

## When NOT to use

- **Pure greenfield work.** There is no passing surface to regress
  against. Use `/specify + /plan + /tasks` and skip this skill.
- **First-ever edit to a repo with no passing tests.** Pre-step:
  capture a minimal manual baseline ("these three URLs return 200")
  OR pair with `test-engineer` to write characterization tests for
  the critical paths first; only then run this skill.
- **Trivial edits that go through `/quick`.** `/quick` bypasses the
  full plan pipeline by design — baseline capture is plan-level.
- **Docs-only or fixture-only edits.** The per-step `files_allowed`
  already restricts scope; a diffable baseline adds no signal.

## Related

- `rules/global/brownfield.md` — iron law "Read existing code + tests
  BEFORE proposing changes." This skill is the mechanisation of that.
- `rules/global/deprecation.md` — when a baseline diff reveals a
  removed endpoint / field, the deprecation policy is what decides
  whether that removal is permitted.
- `rules/global/change-budget.md` — large diffs are more likely to
  blow the baseline; the change-budget rule gates when a plan should
  be split before it even reaches this skill.
- `contract-drift-detection` — captures the *source-of-truth* side of
  a contract; this skill captures the *observable behaviour* side.
  Both gates should be active on any plan that changes a
  cross-stack surface.
- `systematic-debugging` — invoked on every missing line in the
  post-run diff.
- `verification-before-completion` — the Phase 4 diff check is the
  same gate.
