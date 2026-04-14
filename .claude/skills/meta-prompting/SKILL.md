---
name: meta-prompting
description: Use when converting a natural-language goal plus an approved plan into a validated ExecutionPlan JSON for the orchestrator. Produces only JSON, no prose.
---

# Meta-Prompting

## Overview
Meta-prompting is the bridge between human language and deterministic orchestration. Given a goal and an approved plan, emit a single JSON document conforming to `schemas/execution_plan.py::ExecutionPlan`. The orchestrator consumes this directly; any non-JSON output breaks the pipeline.

## Iron Law
```
OUTPUT IS A SINGLE VALID JSON DOCUMENT. NO PROSE, NO MARKDOWN FENCES, NO EXPLANATION.
```

## Process

1. **Load inputs.** Read:
   - Current `CONSTITUTION.md` (capture its path for `constitution_ref`)
   - `specs/<slug>.md` (approved)
   - `.soup/plans/<slug>.md` (approved)
   - `.claude/agents/` (for agent roster — only names in the enum)
2. **Decompose into TaskSteps.** For each bullet in the plan's task list:
   - `id` (S1, S2...)
   - `agent` (from roster)
   - `prompt` (full subagent brief, self-contained)
   - `verify_cmd` (exit-0-pass bash)
   - `files_allowed` (globs, narrow)
   - `depends_on` (other step IDs)
   - `parallel` (bool, true iff disjoint `files_allowed` and no output dependency)
   - `model` (`haiku` for routine, `sonnet` default, `opus` only for architect/migrations — Constitution VIII)
   - `max_turns` (≤10)
   - `rag_queries` (list; empty if none)
3. **Pair every impl step with a prior test-engineer step.** TDD shape (Constitution III.1).
4. **Compute realistic `budget_sec`** including failure buffer.
5. **Validate mentally** against the schema: required fields present, enums correct, globs not `**/*`.
6. **Emit JSON only.** Your stdout is piped into `ExecutionPlan.model_validate_json()`.

## Red Flags

| Thought | Reality |
|---|---|
| "Let me explain my reasoning in prose above the JSON." | The pipeline breaks on the first non-JSON byte. Emit only JSON. |
| "`files_allowed: ['**/*']` — I'm not sure which files." | If you're not sure, research more. Don't guess wide. |
| "Skip the test-engineer step — it's a refactor." | Refactors still need green tests. Pair it. |
| "Use opus for everything — safe default." | Constitution VIII: `opus` only where necessary. Default `sonnet`. |
| "11-turn step — close enough to 10." | Split it. The orchestrator enforces the cap. |
| "Include all the spec in every step's prompt." | Narrow excerpts. Context bloat harms subagent quality. |

## Related skills
- `writing-plans` — the plan meta-prompter consumes
- `executing-plans` — the orchestrator runtime
- `subagent-driven-development` — what each step becomes
- `spec-driven-development` — the enclosing flow
