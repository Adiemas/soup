# GSD (get-shit-done) — Research Report

## Purpose
GSD is a **meta-prompting and context engineering framework** to eliminate "context rot." It provides a spec-driven workflow system for AI coding agents (Claude Code, Gemini CLI, OpenCode, Cursor, Copilot), prioritizing systematic quality over vibecoding.

## Workflow Model (Idea → Merged)

5-phase pipeline:
1. **Initialize** (`/gsd-new-project`) — Questions → Research → Requirements extraction → Roadmap
2. **Discuss** (`/gsd-discuss-phase`) — Lock implementation preferences (layouts, APIs, tone, scope)
3. **Plan** (`/gsd-plan-phase`) — Domain research → XML-structured task plans (2-3 tasks/plan) → Verification loop
4. **Execute** (`/gsd-execute-phase`) — Parallel waves, fresh 200K-token contexts per task → Atomic commits per task
5. **Verify** (`/gsd-verify-work`) — UAT + automated failure diagnosis

**Task model:** XML-wrapped tasks with `name`, `files`, `action`, `verify`, `done` fields. Sized for single context windows. Dependent tasks form "waves".

## Key Commands & Agents

**69 slash commands** including: `/gsd-new-project`, `/gsd-discuss-phase`, `/gsd-plan-phase`, `/gsd-execute-phase`, `/gsd-verify-work`, `/gsd-quick`, `/gsd-map-codebase`, `/gsd-review`.

**24 specialized agents** including: `gsd-planner`, `gsd-executor`, `gsd-verifier`, `gsd-domain-researcher`, `gsd-plan-checker`, `gsd-code-reviewer`.

## Patterns Worth Stealing

1. **Fresh Context Per Agent** — Each spawned agent gets up to 200K tokens; no accumulated conversation rot.
2. **File-Based State Management** — All project state in `.planning/` as Markdown/JSON. No database. Survives context resets.
3. **Wave Execution** — Independent tasks run simultaneously; dependent tasks wait.
4. **Thin Orchestrators** — Workflow files load context, spawn agents, collect results, update state. Never heavy lifting.
5. **XML Task Structuring** — `<task>` elements with explicit `name`, `files`, `action`, `verify`, `done`.
6. **Hook System** — Pre/PostToolUse hooks (bash in `hooks/`): `gsd-validate-commit.sh` (Conventional Commits), `gsd-phase-boundary.sh`, `gsd-workflow-guard.sh`. Opt-in via `.planning/config.json`.
7. **Atomic Commits Per Task** — Enables bisecting failures without full phase rollback.
8. **Decision Fidelity** — Planner treats locked `/gsd-discuss-phase` decisions as NON-NEGOTIABLE constraints.
9. **Verification Gates** — 4 gate types (Confirm, Quality, Safety, Transition) wired into plan-checker and verifier.
10. **Multi-Agent Specialization** — Researchers, planners, checkers, executors, verifiers run in parallel.

## Gaps
- No explicit GitHub/ADO API integration for issue/PR automation (CLI-only)
- Installer is JS/TS/Node.js centric; no Python/C# native tooling
- No built-in Docker orchestration
- No Postgres schema migration planning

## Relevance: 4.5/5

**Recommendation:** Adopt thin orchestrator pattern, file-based state, wave execution, and hook system. Adapt installer for Python/C# targets. Add GitHub/ADO API integration layer. Add Postgres-aware planning agents.
