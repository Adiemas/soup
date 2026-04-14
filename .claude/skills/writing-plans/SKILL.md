---
name: writing-plans
description: Use when you have an approved spec and need to translate it into a TDD-shaped task list before any code is written. Output is a plan markdown in .soup/plans/.
---

# Writing Plans

## Overview
Take an approved spec (+ architect design if present) and produce a bite-sized, TDD-shaped task list. Each task has explicit `files_allowed`, `verify_cmd`, and a named agent. The plan is what the meta-prompter will convert to an `ExecutionPlan` JSON.

## Iron Law
```
EVERY IMPLEMENTATION TASK IS PRECEDED BY A TEST-ENGINEER TASK FOR THE SAME SCOPE. NO EXCEPTIONS.
```

## Process

1. **Read the spec end-to-end.** Enumerate every REQ-N. This is your traceability anchor.
2. **Sketch the file map.** Which modules/components will be created or touched? Constrain to the narrowest surface.
3. **Decompose by behavior, not by file.** A task is "add pagination to list endpoint", not "edit router.py".
4. **Pair each implementation task with a test-engineer task.** The test task's `files_allowed` is test files only.
5. **Write each task with all fields:** `id`, `title`, `agent`, `files_allowed` (globs), `verify_cmd` (exit-0=pass bash), `depends_on`, `parallel` (bool), and a 2-4 sentence prompt body.
6. **Cap tasks at 10 turns.** If you can't articulate a 10-turn path, split.
7. **Check coverage of REQs.** Every REQ must appear in at least one task's acceptance. Flag gaps.
8. **Estimate budget_sec.** Realistic; include failure buffer.

## Red Flags

| Thought | Reality |
|---|---|
| "I'll skip the test task — the impl is trivial." | Constitution III.1: no prod code without failing test. Always pair. |
| "Let me use `files_allowed: ['**']` for now." | That's not a boundary; it's giving up. Name the files. |
| "`verify_cmd: echo done`" | Not a verification. Run the real assertion. |
| "One task, many files, many behaviors — move fast." | That task will balloon past 10 turns and fail review. Split. |
| "We don't need `depends_on` — the agent will figure it out." | The orchestrator plans waves from `depends_on`. Without it, parallelism breaks. |

## Related skills
- `brainstorming` — run before writing a plan
- `meta-prompting` — converts this plan to executable JSON
- `executing-plans` — what happens next
- `tdd` — the discipline every task must encode
