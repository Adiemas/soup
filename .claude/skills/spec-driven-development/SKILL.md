---
name: spec-driven-development
description: Use for any non-trivial feature or change. Establishes the canonical /constitution → /specify → /clarify → /plan → /tasks → /implement → /verify flow.
---

# Spec-Driven Development

## Overview
Non-trivial work flows through a fixed phase sequence. Each phase has a canonical command, a canonical artifact, and a canonical gate. Specs describe outcomes; plans describe approach; tasks describe bite-sized deliveries; implementation is gated by TDD and verify.

## Iron Law
```
/specify → /clarify → /plan → /tasks → /implement → /verify. SKIP NO PHASE FOR NON-TRIVIAL WORK.
```

## Process

1. **`/constitution`** (one-time per project). Confirm principles exist in `CONSTITUTION.md`. If missing or stale, write them first.
2. **`/specify "<goal>"`.** `spec-writer` produces `specs/<slug>.md` with EARS requirements, acceptance criteria, out-of-scope. What + outcomes only — no tech.
3. **`/clarify`.** Surface open questions, resolve interactively with human. Update spec. Approve + freeze.
4. **`/plan`.** `architect` (if design decisions needed) + `plan-writer` produce `.soup/plans/<slug>.md`. Tech choices, file map.
5. **`/tasks`.** `plan-writer` breaks plan into TDD-shaped tasks, each with `files_allowed`, `verify_cmd`, agent, dependencies.
6. **`/implement`.** `meta-prompter` emits `ExecutionPlan` JSON → `orchestrator` runs waves → `qa-orchestrator` gates.
7. **`/verify`.** QA gate: reviewer + scanner + test runner in parallel; verdict APPROVE/NEEDS_ATTENTION/BLOCK.

Use `/quick <ask>` ONLY for trivial one-liners (typo, comment, single-line refactor). Everything else: the full flow.

## Red Flags

| Thought | Reality |
|---|---|
| "Small feature — skip spec." | "Small" features are where drift hides. Write the spec; it's 10 minutes. |
| "Spec + plan = paperwork, just code it." | The planning time pays back on wave 3 when an agent asks "what's the acceptance?". |
| "Spec names the library." | That's tech. Move to `/plan`. Spec stays what-and-outcomes. |
| "`/clarify` is optional." | If the spec has any ambiguity, clarify. Guessing = rework. |
| "Run `/implement` before `/tasks`." | Meta-prompter needs decomposed tasks. `/tasks` is not skippable. |

## Related skills
- `brainstorming` — before `/specify`
- `writing-plans` — the `/plan` + `/tasks` phase
- `meta-prompting` — inside `/implement`
- `executing-plans` — orchestrator runtime
- `tdd` — each task's internal discipline
