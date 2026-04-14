---
description: Run orchestrator on an ExecutionPlan. Waves of fresh subagents, worktree isolation, atomic commits, QA gate.
argument-hint: [plan-json-path]
---

# /implement

## Purpose
Execute a validated ExecutionPlan. Orchestrator handles waves, subagent spawning, verification, and atomic commits. Stop hook runs QA gate.

## Variables
- `$ARGUMENTS` — optional plan JSON path; defaults to most recent `.soup/plans/*.json`.

## Workflow
1. Invoke `orchestrator` (opus) with plan path.
2. Orchestrator loop:
   - If `plan.regression_baseline_cmd` is set, run it once **before** the first wave; artefact → `.soup/baseline/<run_id>/pre.txt`. See the `brownfield-baseline-capture` skill for authoring the command.
   - Compute waves (see `orchestrator/waves.py`).
   - For each wave, spawn fresh subagents per step (parallel where allowed) via `orchestrator/agent_factory.py`.
   - Each subagent: runs in worktree, sees only `files_allowed` + injected rules + RAG context, ≤ `max_turns` turns.
   - On step exit: run `verify_cmd`; on pass, atomic commit; on fail, dispatch `verifier` (fix-cycle role) with `systematic-debugging` context (≤3 attempts, then escalate to architect).
3. Persist `.soup/runs/<run_id>.json` after each step.
4. If baseline was captured and the run passed all waves, run `plan.regression_baseline_cmd` again → `post.txt`, write unified diff → `diff.txt`. Any previously-passing line missing in `post.txt` marks `RunState.status = "regression"`; the QA gate treats this as a high-severity finding (does not auto-reject).
5. On plan completion: Stop hook triggers `qa-orchestrator` → QAReport. If `regression_baseline_diff_path` is set on `RunState`, the QA gate reads the diff and attaches it as a finding.
6. Report outcome to user.

## Output
- Run ID.
- Per-wave status table.
- Commits produced (SHA list).
- Baseline diff path (when `regression_baseline_cmd` was set).
- Final QAReport verdict + findings.
- Next step: `/verify` or `gh pr create` (on APPROVE).

## Notes
- If `budget_sec` exceeded: hard abort, log to `logging/experiments.tsv`. Post-run baseline is skipped on abort; the pre-file is preserved for post-mortem.
- Never bypass QA BLOCK. Fix and re-run.
- Partial-wave failure: remaining waves skipped; state preserved for resume.
- `regression` status is distinct from `failed` — all waves passed, but the
  baseline diff flagged a regression. The QA gate decides whether to merge,
  request operator review, or BLOCK. Do not override the diff without a
  written rationale in the PR body.
