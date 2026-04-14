---
name: executing-plans
description: Use when you have a written plan to execute. Runs tasks in bite-sized batches with explicit human checkpoints and wave-level verification.
---

# Executing Plans

## Overview
Once a plan exists in `.soup/plans/<slug>.md` and has been converted to a validated `ExecutionPlan`, you execute it in waves. Each wave spawns fresh subagents per task, verifies, commits atomically, and checkpoints with the human where configured.

## Iron Law
```
NO WAVE PROGRESSES UNTIL EVERY TASK IN THE PRIOR WAVE HAS A GREEN verify_cmd AND AN ATOMIC COMMIT.
```

## Process

1. **Load the ExecutionPlan.** Validate it against `schemas/execution_plan.py`. Reject malformed.
2. **Compute waves.** Topological sort by `depends_on`; tasks with `parallel: true` and no unmet deps form a wave.
3. **Dispatch the wave.** One fresh subagent per task (via `Agent` tool or orchestrator). Pass only the task's own fields — no upstream chatter.
4. **Wait for all tasks in the wave.** Collect results. Run each `verify_cmd` fresh.
5. **Commit per task.** Conventional Commits (`feat(scope): ...`). One task = one commit. If verify fails, dispatch `verifier` (fix-cycle role) and retry (max 3 per task).
6. **Checkpoint the human** between waves in `go-i` mode. Show: tasks completed, commits made, next wave preview. Wait for "go".
7. **On plan completion,** dispatch `qa-orchestrator` for the QA gate. Relay verdict.

## Red Flags

| Thought | Reality |
|---|---|
| "Skip verify this time, it's a tiny change." | Every task has a `verify_cmd` for a reason. Run it. Quote it. |
| "Commit everything at the end, it's cleaner." | Atomic per-task commits enable bisect. Bulk commits break recovery. |
| "Let me do wave 2 while wave 1 finishes — save time." | Wave boundaries exist because downstream depends on upstream commits. Wait. |
| "Fix-cycle looped 4 times; one more will do it." | Constitution IX.1: 3 strikes → escalate to architect. |
| "I'll merge the worktree before QA." | Constitution IV: only APPROVE permits merge. Gate first. |

## Related skills
- `writing-plans` — what you're executing
- `subagent-driven-development` — the per-task dispatch model
- `dispatching-parallel-agents` — wave execution
- `verification-before-completion` — the per-task gate
- `using-git-worktrees` — isolation for the run
