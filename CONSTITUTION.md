# Soup Constitution

_Hard rules for every project built with this framework. Override only with explicit written dispensation in the project `CLAUDE.md`._

## Article I — Specification

1. Every feature begins with a spec in `specs/` using EARS requirements ("The system shall...").
2. Specs describe **what** and **outcomes**, never **how**. Tech choices live in `/plan`.
3. Ambiguities must be resolved via `/clarify` before `/plan`. No guessing.
4. Approved specs are frozen. Changes require a new spec version, not an edit.

## Article II — Planning

1. Every plan must validate against `schemas/execution_plan.py::ExecutionPlan`.
2. Each `TaskStep` must declare: `files_allowed` (glob), `verify_cmd` (bash), `depends_on`, `model`.
3. Tasks >10 turns must be split. No unbounded subagents.
4. `budget_sec` caps total plan wall-clock. Exceeding → orchestrator aborts.

## Article III — Implementation

1. TDD red-green-refactor is mandatory. `test-engineer` writes the failing test first; `implementer` makes it pass; only then refactor.
2. One `TaskStep` = one atomic commit. Conventional Commits format (`feat(scope): ...`).
3. `files_allowed` is enforced by `pre_tool_use` hook. Out-of-scope edits are rejected.
4. Every new Python module has type hints (mypy strict) and a docstring.
5. Every new C# class has XML doc comments and nullable reference types enabled.
6. React components are functional, hooks-based, TypeScript-typed; no class components.
7. Each PR respects `rules/global/change-budget.md` — /quick ≤ 20 LOC, normal ≤ 200 LOC, architect pre-pass 200-1000 LOC, split beyond that. Breaking changes route through `rules/global/deprecation.md`.

## Article IV — Quality Gate

1. Stop hook triggers `qa-orchestrator` on every substantive edit session.
2. QA verdict BLOCK on: any failing test, any critical security finding, ≥3 critical correctness findings.
3. QA verdict NEEDS_ATTENTION on: coverage <70%, or ≥3 medium findings.
4. Only APPROVE permits merge/PR.

## Article V — Data & Migrations

1. All Postgres schema changes ship as migrations (one forward, one back).
2. No raw DDL in runtime code.
3. Dev/CI/prod share the same migration files; environments diverge only via config.
4. `sql-specialist` agent is the sole author of migrations.

## Article VI — Secrets

1. No secrets in code, prompts, or logs.
2. `.env` is loaded by `session_start` hook; `.env.example` is the contract.
3. Pre-commit hook scans for high-entropy strings and common key prefixes.
4. Session logs redact values of any key matching `(?i)(secret|token|key|password)`.

## Article VII — Memory & Context

1. `CLAUDE.md` is the session steering. Keep it under 500 lines.
2. `MEMORY.md` is long-term, append-mostly. Prune only with explicit user instruction.
3. RAG retrievals must cite `[source:path#span]` — no uncited claims.

## Article VIII — Cost discipline

1. `haiku` for: routine research, log summaries, command wrapping, single-file edits.
2. `sonnet` default for: implementer, code-reviewer, most subagents.
3. `opus` only for: `orchestrator`, `meta-prompter`, `architect`, `sql-specialist` (migrations).
4. Every plan declares `budget_sec`. Agents exceeding → hard stop, log to experiments.tsv.

## Article IX — Failure handling

1. 3 failed fix attempts on the same bug → `systematic-debugging` skill mandatory + escalate to architect.
2. Verify failure → auto-dispatch `verifier` (fix-cycle role) with full failure context + spec excerpt.
3. Broken worktree → discard, re-plan. Never commit partially-working state to main.

## Article X — Change to this constitution

The constitution is edited via `/constitution` command only. Every edit:
1. Requires a rationale captured in the commit body.
2. Invalidates in-flight plans; they must be re-validated.
3. Bumps `constitution_ref` in future `ExecutionPlan`s.
