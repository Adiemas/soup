# Soup — Agentic Framework for Streck Internal Apps

This repo is the canonical agentic Claude Code framework. Use the opinionated flow.

> **First session in this repo?** Read [`docs/ONBOARDING.md`](docs/ONBOARDING.md)
> before anything else — it walks through `just init`, `.env` setup,
> and the first `just go` in ~30 minutes. Come back here once you have
> a feature ticket in hand; this file is steering for every subsequent
> session.

## Non-negotiable iron laws

1. **No production code without a failing test first.** TDD is gated by the `tdd` skill + Stop-hook QA gate. Pre-test code is deleted.
2. **No implementation before a written plan for non-trivial work.** Use `/plan` and `/tasks`. Trivial one-liners can use `/quick`.
3. **Fresh subagent per substantive task.** Invoke via `orchestrator` or `subagent-driven-development` skill — no inline multi-hour sessions.
4. **Evidence before claims.** Run `verify_cmd`, read the output, quote it. Never say "done" without checked output.
5. **Root cause over symptom.** `systematic-debugging` skill applies on every bug. 3 failed fix attempts → escalate.
6. **Cite RAG retrievals.** Every claim backed by retrieved docs must include `[source:path#span]`.

## Stack (internal apps this framework builds)

- **Python** (FastAPI / Typer CLIs, pytest, uv/pip, ruff, mypy) — preferred
- **C# / .NET 8** (ASP.NET Core, xUnit, dotnet CLI)
- **React + TypeScript** (Vite, React Testing Library, playwright)
- **PostgreSQL 16** (sqlc for Python, EF Core for .NET)
- **Docker** (multi-stage builds, docker-compose for local)
- **GitHub** (PR flow, Actions) + **Azure DevOps** (work items, pipelines, repos)

## Canonical flow

```
/constitution   → define project principles (one-time)
/specify "..."  → user-facing spec (what + outcomes)
/clarify        → resolve ambiguities (HITL)
/plan           → architecture + tech choices
/tasks          → TDD-shaped task list with boundaries
/implement      → orchestrator executes waves of fresh subagents
/verify         → QA gate (code-review + security + tests)
```

For ad-hoc: `/quick "<ask>"` (skips spec/plan — use only for trivial changes).

## Agent dispatch

Use the top-level `orchestrator` agent for anything >1 step. It calls `meta-prompter` (opus) to produce an `ExecutionPlan` JSON (validated by `schemas/execution_plan.py`), then runs waves of fresh subagents with worktree isolation.

Never let an agent span >10 turns. Split the task.

## Rules routing (automatic)

Editing `.py` → `rules/python/*.md` injected by `pre_tool_use` hook.
Editing `.cs` → `rules/dotnet/*.md`.
Editing `.tsx` / `.ts` → `rules/react/*.md` or `rules/typescript/*.md`.
Editing `.sql` → `rules/postgres/*.md`.
Always: `rules/global/*.md`.

## Memory

- `CLAUDE.md` (this file) — steering context; always in window
- `MEMORY.md` — long-term facts, decisions, incidents
- `.soup/memory/` — per-project dream-consolidated summaries
- `logging/agent-runs/*.jsonl` — per-session tool-call trace
- `logging/experiments.tsv` — append-only metric table (autoresearch-style)

## What NOT to do

- Don't edit files outside your assigned `files_allowed` glob.
- Don't skip the Stop hook. If QA blocks, fix and re-verify — don't bypass.
- Don't use `--no-verify` on commits. Never.
- Don't write `pass` / `TODO` / stubs as "done."
- Don't add dependencies without updating `pyproject.toml` + rationale in PR.
- Don't commit secrets. Session-start hook validates.
