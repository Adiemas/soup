---
name: dispatching-parallel-agents
description: Use when facing 2+ independent tasks with no shared state or sequential dependencies. Spawns concurrent subagents and groups failures by domain.
---

# Dispatching Parallel Agents

## Overview
When tasks are genuinely independent, dispatch them in parallel. A wave completes when every branch does. Failures are grouped by domain for efficient follow-up.

## Iron Law
```
PARALLEL ONLY WHEN files_allowed IS DISJOINT AND NO TASK DEPENDS ON ANOTHER'S OUTPUT.
```

## Process

1. **Prove independence.** For every pair (A, B):
   - `files_allowed(A) ∩ files_allowed(B) = ∅` (disjoint file globs)
   - B does not read any artifact produced by A in this wave
   - If either check fails, put them in sequential waves instead.
2. **Compose briefs for each.** Same discipline as `subagent-driven-development`.
3. **Dispatch concurrently** — one `Agent` tool call per task in the same message block.
4. **Await the whole wave.** Do not process partial results as "good enough".
5. **Group outcomes by domain** — all green in domain X, all red in domain Y. Makes debugging tractable.
6. **Commit per task,** not per wave. Preserves bisect.
7. **Fix-cycle failures in parallel** only if their failures are independent; otherwise serialize.

## Red Flags

| Thought | Reality |
|---|---|
| "They probably don't conflict — parallel is faster." | Prove disjoint `files_allowed`. Hunches cause merge conflicts. |
| "Task B needs task A's output — I'll just run them together and fix up." | That's sequential. Declare the dependency. |
| "Wave had 8 tasks; 1 failed — call it a pass." | Failures block the wave. All green or no progress. |
| "Parallelize everything, even test-engineer + implementer." | Impl depends on the failing test. Hard sequential pair. |
| "Let me give each subagent the same giant spec." | Narrow excerpts per task. Parallel compounds the context-bloat cost. |

## Related skills
- `subagent-driven-development` — each branch is a fresh subagent
- `executing-plans` — waves are the parallel unit
- `using-git-worktrees` — isolation keeps concurrent edits sane
