# Real-world dogfood — Warhammer 40k Calculator

**Date:** 2026-04-14
**Target repo:** `C:\Users\ethan\CodeProjects\warhammer-40k-calculator`
**Framework under test:** `soup` at `C:\Users\ethan\AIEngineering\soup`
**Mode:** Propose-only. Read-mostly.

---

## Target snapshot

**Stack.** Full-stack monorepo with npm workspaces at the root.

- **Frontend:** React 18 + TypeScript + Vite + Tailwind + Chart.js/D3 + Socket.IO + React Query.
- **Backend:** FastAPI (Python 3.11/3.12 intended, but the venv on disk shipped Python 3.13), async SQLAlchemy 2.0, Pydantic v2, Alembic migrations, Redis, WebSockets. 58 FastAPI routes across ML, auth, community, calculations, websocket, units, weapons.
- **Database:** PostgreSQL in production, SQLite fallback for dev (~42 tables). `database/migrations/` and `database/seeds/`. `docker/docker-compose.yml` exists.
- **Tests:** `tests/test_complete_backend.py` + `tests/test_complete_frontend.py` at the root; backend has debug scripts (`debug_combat.py`, `debug_saves.py`, `debug_hit_rate.py`, `debug_api_detailed.py`) and bespoke runners (`test_combat_validation.py`, `test_api_endpoints.py`, `test_api_endpoints_fixed.py`, `test_enhanced_calculator.py`). Frontend has `integration-test-suite.js` and `test-backend-connectivity.js`.

**Scale.** Large, sprawling. ~95% complete per `CLAUDE.md`. Bespoke code rather than scaffolded. Implementation pre-dates Soup.

**State of the multi-agent setup.** This is the headline finding: the repo already ran a **document-driven multi-agent pipeline** over many sessions.

- 7 agent specs (`AGENT_*_SPEC.md`) — each a standalone markdown ~200-500 lines with mission, duration, phases, concrete commands, success criteria.
- 1 master plan (`MASTER_AGENT_EXECUTION_PLAN.md`) — DAG-like phase sequencing (Phase 1 Foundation → Phase 2 Core Features → Phase 3 QA), explicit `depends on` language, 7 agents with priority/duration/status columns.
- 3 status files (`AGENT_DATABASE_FIXER_STATUS.md`, `AGENT_FRONTEND_INTEGRATION_STATUS.md`, `AGENT_API_VALIDATOR_STATUS.md`, `AGENT_COORDINATOR_FINAL_STATUS.md`) — completion reports.
- 4 handoff docs (`CURRENT_STATUS_HANDOFF.md`, `PROJECT_HANDOFF.md`, `SESSION_STATUS_CURRENT.md`, `AGENT_COORDINATOR_FINAL_STATUS.md`) — multiple overlapping sources of truth.
- `.claude/settings.json` is trivial (just `additionalDirectories`) — none of this uses Claude Code's subagent mechanism. The "agents" are humans-in-chat running Claude Code sessions with these specs pasted in.
- A `venv/` checked into the tree alongside `python-3.12.7-amd64.exe` and six `requirements*.txt` variants (`-minimal`, `-core`, `-compatible`, `-python312`, `-python313`).

---

## The repo's multi-agent approach vs soup

| Concern | Warhammer repo | Soup |
|---|---|---|
| **Agent definition** | Free-form markdown specs. Each `AGENT_*_SPEC.md` embeds mission, phase-by-phase scripts, code snippets, acceptance criteria. Hundreds of lines each. | YAML-front-mattered `.claude/agents/*.md` with `name`, `description`, `tools`, `model`. Short; role-scoped; no project specifics. Project specifics live in the `TaskStep.prompt`. |
| **Orchestrator** | `MASTER_AGENT_EXECUTION_PLAN.md` — prose DAG. Human reads it, opens the right spec, pastes it in. No programmatic validation. | `schemas/execution_plan.py` (Pydantic). Validates acyclic graph, depends-on references, agent-in-roster, `verify_cmd` allowlist, file-scope globs, `max_turns`, `env` allowlist. Produced by `meta-prompter` (opus), consumed by orchestrator. |
| **Handoff / state** | `CURRENT_STATUS_HANDOFF.md` + `PROJECT_HANDOFF.md` + `SESSION_STATUS_CURRENT.md` + `AGENT_*_STATUS.md` — prose, hand-maintained, drifts. | `.soup/runs/<run-id>/` trace JSON + `qa-report`, `.soup/memory/` consolidated summaries, `logging/agent-runs/*.jsonl` per-call trace, `logging/experiments.tsv` append-only metrics. Machine-structured. |
| **TDD gate** | Specs mention testing, but `debug_*.py` and multiple `test_api_*.py` variants suggest test-last iteration. | `tdd` skill + Stop-hook QA gate. `test-engineer` role cannot write production code (`files_allowed` scoped to tests). |
| **Verification** | Each status doc self-reports "COMPLETED SUCCESSFULLY" with checklists. No programmatic gate. | `verify_cmd` per step + `verifier` agent + `qa-orchestrator` fan-out (code-review + security + tests) on every Stop. |
| **Python version / venv** | `PYTHON313_FIX.md` hand-crafted doc; 6 requirements files; `python-3.12.7-amd64.exe` committed to tree. | None. `pyproject.toml`, `uv` recommended. No concept of "this project needs Python X; here's the fix pattern for Python Y." |
| **Fresh-context isolation** | One human Claude session per phase; context accumulates. | Subagent per TaskStep, fresh context, `max_turns` cap. |
| **Docker-compose dev loop** | `docker/docker-compose.yml` exists, `npm run dev` uses `concurrently` for frontend+backend. No coordinated Docker dev loop. | `docker/docker-compose.yml` brings up Postgres + dev container. Frontend/backend dev loop not first-class. |
| **Cross-language debug** | Bug ownership implicit. `debug_*.py` files in backend, `test-backend-connectivity.js` in frontend. Neither side owns the cross-stack contract. | `systematic-debugging` skill is stack-agnostic but `python-dev` / `react-dev` specialists are single-stack. No explicit cross-stack debug role. |

**What's better in the warhammer repo.**
1. Specs are **project-specific and actionable**. A new session can paste in `AGENT_COMBAT_CALCULATOR_SPEC.md` and immediately know the formulas, file paths, test cases.
2. `PYTHON313_FIX.md` is a concrete, reusable runbook pattern — Soup has nothing like this.
3. `MASTER_AGENT_EXECUTION_PLAN.md` has a readable "quick reference" table with priority/duration/status — excellent for human scan.
4. `requirements-*.txt` matrix acknowledges Python-version reality in a way `pyproject.toml` alone does not.

**What's worse.**
1. Prose-only DAG. Cycles and missing deps are uncaught until a human trips on them.
2. Status drift across 4+ handoff files. Dates stop at 2025-07-01.
3. No fresh-context enforcement. Context-window exhaustion likely caused the "ML router disabled" and "TypeScript warnings non-blocking" resignations.
4. Debug scripts multiply (`debug_combat.py`, `debug_saves.py`, `debug_fnp.py`, `debug_hit_rate.py`) — TDD would collapse these into one suite.
5. Self-reported "COMPLETED SUCCESSFULLY" without independent QA.

---

## Scenarios

### Scenario A — Execute a work item from existing plan

**Pick:** `AGENT_COMBAT_CALCULATOR_SPEC.md`. This is the meaty one — three phases, formulas for hit/wound/save probabilities, Monte Carlo simulation, acceptance tests against published 40k rules.

**Translation to Soup's `ExecutionPlan`.** The spec maps to four TaskSteps:

```json
{
  "goal": "Implement and validate Warhammer 40k combat calculator with Monte Carlo simulation",
  "constitution_ref": "CONSTITUTION.md",
  "budget_sec": 10800,
  "worktree": true,
  "steps": [
    {
      "id": "S1",
      "agent": "test-engineer",
      "prompt": "Write failing pytest tests for hit_probability, wound_probability, save_probability, expected_damage. Use rules-sourced oracle values for Space Marine (WS3+, S4, T4, Sv3+) vs Ork Boy (WS4+, T4, Sv6+). Include edge cases: S >= 2T (2+ to wound), ineligible saves (mod > 6).",
      "depends_on": [],
      "parallel": false,
      "model": "sonnet",
      "verify_cmd": "! pytest backend/tests/test_combat_math.py",
      "files_allowed": ["backend/tests/test_combat_math.py"],
      "max_turns": 8
    },
    {
      "id": "S2",
      "agent": "python-dev",
      "prompt": "Implement hit/wound/save probability functions + expected_damage in backend/app/services/combat_calculator.py to pass tests from S1.",
      "depends_on": ["S1"],
      "verify_cmd": "pytest backend/tests/test_combat_math.py",
      "files_allowed": ["backend/app/services/combat_calculator.py"],
      "max_turns": 10
    },
    {
      "id": "S3",
      "agent": "test-engineer",
      "prompt": "Write failing tests for Monte Carlo simulation: n=10000 iterations, assert mean within 3 sigma of analytic expected_damage.",
      "depends_on": ["S2"],
      "verify_cmd": "! pytest backend/tests/test_combat_monte_carlo.py",
      "files_allowed": ["backend/tests/test_combat_monte_carlo.py"],
      "max_turns": 6
    },
    {
      "id": "S4",
      "agent": "python-dev",
      "prompt": "Implement Monte Carlo simulation with numpy-less fallback (Python 3.13 env).",
      "depends_on": ["S3"],
      "verify_cmd": "pytest backend/tests/test_combat_monte_carlo.py backend/tests/test_combat_math.py",
      "files_allowed": ["backend/app/services/combat_calculator.py"],
      "max_turns": 12
    },
    {
      "id": "S5",
      "agent": "verifier",
      "prompt": "Run full combat test suite + coverage report. Reject if <70%.",
      "depends_on": ["S4"],
      "verify_cmd": "pytest backend/tests/ --cov=app/services/combat_calculator --cov-fail-under=70",
      "files_allowed": [],
      "max_turns": 4
    }
  ]
}
```

**What's lost in translation.**
- The spec's narrative scaffolding — "Phase 1: Combat Rules Analysis" with prose describing the game — compresses into a flat DAG. Domain knowledge gets stripped unless preserved in a `spec` doc.
- The spec lists ~30 specific edge cases across damage types, army-wide modifiers, feel-no-pain rolls, etc. A single TaskStep prompt can't carry all of them without becoming a mini-spec itself.
- Hand-written acceptance criteria ("Space Marine vs Ork Boy produces 0.7 expected damage") become raw test assertions — loses the "why this oracle?" context.

**What's gained.**
- `verify_cmd` with `!` prefix enforces TDD RED phase deterministically.
- `files_allowed` prevents the `test-engineer` from sneaking in production code.
- Cycle detection catches planning bugs.
- Atomic commits per TaskStep → bisect recovery if S4 breaks S2.
- Fresh context per step avoids the context-bleed that led to `debug_hit_rate.py`, `debug_saves.py`, `debug_fnp.py` all coexisting.

**Would Soup's test-engineer + specialist + verifier chain work here?** Yes, cleanly, for the math core. The chain would struggle when the work bleeds into API routes + frontend wiring (see Scenario B). For the calculator service specifically, this is a textbook Soup use case — pure-function logic with clear oracle values.

---

### Scenario B — Debug cross-stack issue

**Scenario:** Frontend shows stale unit data after a backend Alembic migration added a new `point_cost` column. Frontend's React Query cache is happy; the calculator view shows 0 points for all units. Postgres (or SQLite fallback) has the right data. The backend `/api/v1/units/` endpoint returns correct JSON in curl. The bug crosses Python → FastAPI → OpenAPI schema → generated TS types → React Query key → component render.

**Soup flow via `systematic-debugging` skill.**

1. **Reproduce deterministically.** A TaskStep dispatches `verifier` with `verify_cmd: "docker compose up -d && cd backend && pytest backend/tests/test_units_api.py::test_unit_has_point_cost"`. Confirms backend contract. Evidence: JSON response body quoted.
2. **Dispatch `python-dev` subagent** to check: does the SQLAlchemy model actually expose `point_cost`? Does the Pydantic response schema include it? Does Alembic's `autogenerate` detection see it? Files: `backend/app/models/units.py`, `backend/app/schemas/units.py`, `backend/alembic/versions/`. Fresh context avoids dragging in frontend noise.
3. **Dispatch `react-dev` subagent** (in parallel, since backend confirmation is independent) to check: is the frontend TypeScript type regenerated from the latest OpenAPI? Is the React Query key parameterized by a cache-busting version? Files: `frontend/src/services/units.ts`, `frontend/src/types/units.ts`, `frontend/src/hooks/useUnitDatabase.ts`.
4. **Cross-stack gap.** Here Soup's isolation **hurts**. Neither subagent can see the contract drift. The real bug is that `frontend/src/types/units.ts` is hand-written, not generated from OpenAPI, so it never picked up `point_cost`. Neither the python-dev nor react-dev has the integration view. A `full-stack-integrator` role or an explicit `contract-test` step is missing.
5. **Workaround today.** The `orchestrator` / `architect` can sequence a third TaskStep with `agent: verifier`, `prompt: "Diff backend OpenAPI schema against frontend TS types and report mismatches"`, `verify_cmd: "python scripts/check_openapi_drift.py"`. But that script doesn't exist, so in practice this cross-stack class of bug falls through Soup's net until the human rebuilds the bridge.

**Verdict.** Subagent isolation is a net win for same-stack debugging (keeps context focused, enforces `files_allowed`), but it **actively hurts** contract-crossing bugs unless the plan explicitly includes a contract-drift verifier. Soup needs a dedicated skill/agent for this. The warhammer repo's implicit coupling via `AGENT_FRONTEND_INTEGRATION_SPEC.md` (a single human agent touching both sides) handles this better by default, at the cost of context pollution.

---

### Scenario C — Refactor/Docs: consolidating planning docs

**The pile.** `MASTER_AGENT_EXECUTION_PLAN.md` (DAG + timeline + reference table), `PARALLEL_DEVELOPMENT_PLAN.md` (6-agent parallel task breakdown — older, overlaps MASTER), `PROJECT_HANDOFF.md` (pre-Pydantic-fix era, 460 lines), `CURRENT_STATUS_HANDOFF.md` (post-fix, 230 lines), `SESSION_STATUS_CURRENT.md` (Python 3.13 install crisis), `AGENT_COORDINATOR_FINAL_STATUS.md`, four `AGENT_*_SPEC.md`, four `AGENT_*_STATUS.md`.

**Soup target layout.**

- `specs/combat-calculator.md`, `specs/api-validation.md`, `specs/frontend-integration.md`, `specs/auth-data-flow.md`, `specs/test-infrastructure.md`, `specs/performance-security.md` — one spec per feature, using Soup's `spec-writer` template.
- `.soup/plans/20260414-master.json` — single ExecutionPlan replacing `MASTER_AGENT_EXECUTION_PLAN.md` + `PARALLEL_DEVELOPMENT_PLAN.md`.
- `.soup/runs/<run-id>/` populated from the three completed `AGENT_*_STATUS.md` files (database-fixer, frontend-integration, api-validator).
- `MEMORY.md` — long-term incident facts (Pydantic v2 migration, Python 3.13 compat, ARRAY→JSON for SQLite, pandas pinning).
- `docs/runbooks/python313.md` — new runbook genre (Soup doesn't have this yet) salvaging `PYTHON313_FIX.md`.
- `CURRENT_STATUS_HANDOFF.md` and `SESSION_STATUS_CURRENT.md` — delete; superseded by `.soup/runs/` and `logging/experiments.tsv`.

**Loss.**
- **Narrative cohesion.** `PROJECT_HANDOFF.md` reads like a handoff letter; human-warm. JSON DAG + structured specs are readable-enough but clinical.
- **"Expected timeline" section** (Day 1/Day 2/Day 3 breakdowns in the master plan) has no natural home in Soup. Could attach as a `budget_sec` comment but loses the phased narrative.
- **Multi-audience framing.** The existing docs simultaneously brief next-agent, explain-to-stakeholder, and document-architecture. Soup's split (`spec` for scope, `plan` for DAG, `MEMORY.md` for durable facts) forces separation. Benefits the machine; costs the skim-reader.
- **Cross-linked "read these four files first" onboarding.** Recreating that in Soup requires an index page under `docs/`.

**Gain.**
- **Single source of truth** for status (runs + memory).
- **Plans are executable**, not prose.
- **Drift prevention** — mtime on `specs/*.md` is the owning artifact; status is derived.
- **Agent compatibility** — a fresh `meta-prompter` run can re-derive the DAG from the consolidated specs, whereas the prose plans need a human to re-read.
- **Deletion of `python-3.12.7-amd64.exe`** (!) and the 6 `requirements*.txt` variants in favor of `pyproject.toml` + a runbook.

---

## Lessons soup should adopt from this repo

This repo is roughly 4 months ahead of Soup in several grooves worth stealing.

1. **Project-specific agent briefs.** Soup agents (`.claude/agents/*.md`) are generic role definitions. The warhammer `AGENT_*_SPEC.md` files embed domain formulas, file paths, edge cases. Soup should recognise that `TaskStep.prompt` alone is too thin for complex work — it needs a **spec-snippet include** mechanism, so a TaskStep can reference `specs/combat-calculator.md#phase-1` and the spec content is attached to the child subagent's prompt automatically.
2. **Master-plan quick-reference table.** The "| Agent | Priority | Duration | Status | Key Deliverable |" table in `MASTER_AGENT_EXECUTION_PLAN.md` is more scannable than any JSON DAG Soup produces today. Soup's `just plan` should emit a markdown preview alongside the JSON.
3. **Runbook files for environmental pain.** `PYTHON313_FIX.md` is a genre Soup lacks entirely. A `docs/runbooks/` directory with Python/Docker/Postgres/Node known-failure recipes would save every Soup project its first two sessions. This directly addresses the "why did my setup hang for 40 min" tax on new users.
4. **Requirements-matrix pattern.** `requirements-python312.txt` + `requirements-python313.txt` + `requirements-minimal.txt` is ugly but honest: different Python versions need different pins. Soup's `pyproject.toml` with `uv` hides this reality. A `pyproject.toml` + per-Python-version constraint files pattern (documented as optional) would help teams on legacy Python.
5. **Phase-based status markers.** The `✅ COMPLETED` / `🔄 IN PROGRESS` / `📋 QUEUED` / `⚠️ BLOCKED` vocabulary is simple and universally readable. Soup's JSONL traces are machine-rich but don't have a human-readable phase badge. A `.soup/runs/<run-id>/STATUS.md` regenerated on every Stop would close this gap.
6. **Debug script retention.** The `debug_combat.py`, `debug_saves.py`, `debug_fnp.py` pattern, while anti-TDD, *did* give the team throwaway reproduction tools. Soup's TDD purity would delete these — but the `systematic-debugging` skill could formalise a `debug/` directory with TTL so exploration code has a legitimate home.
7. **Cross-stack integration brief.** `AGENT_FRONTEND_INTEGRATION_SPEC.md` explicitly spans frontend + backend + deps check + websocket. Soup has no analog; its specialists are stack-siloed.

---

## Concrete soup gaps

1. **Python venv/version troubleshooting.** No equivalent of `PYTHON313_FIX.md`. If a user hits `module 'pkgutil' has no attribute 'ImpImporter'`, Soup's session-start hook says nothing. No detection of Python-version-sensitive packages (numpy, pandas, asyncpg, psycopg2-binary), no fallback constraint file, no `doctor` subcommand for interpreter/venv sanity checks beyond `just doctor` shell stubs.
2. **Cross-language debug coordination.** `systematic-debugging` is single-stack. No role owns the OpenAPI ↔ generated-TS contract. No automated schema-drift check. No `full-stack-debugger` / `contract-verifier` / `integration-test-writer` agent.
3. **Handoff/status file patterns for long-running projects.** `.soup/runs/` assumes one run at a time. When a project spans months across many runs (as warhammer did), there's no "what's the current state?" aggregation. `MEMORY.md` is too coarse; `runs/` is too fine. A `.soup/status.md` auto-generated rollup is missing.
4. **Existing-planning-docs → ExecutionPlan converter.** To onboard a repo like warhammer-40k-calculator, Soup needs a `just ingest-plans <dir>` that parses prose DAGs (phase language, "Agent X depends on Agent Y") into an ExecutionPlan skeleton. Today a human has to rewrite by hand.
5. **Docker-compose-first dev loop (backend + frontend + db).** Soup's `docker-compose.yml` runs Postgres + dev container, not the app. The warhammer pattern (`npm run dev` → `concurrently` starts both) is the dominant internal-app reality. Soup's `fullstack-python-react` template should ship a compose file that runs frontend + backend + postgres + redis + optional seed as `just dev`.
6. **Frontend + backend integration test orchestration.** The warhammer root-level `tests/test_complete_backend.py` + `tests/test_complete_frontend.py` + `tests/run_all_tests.py` pattern is the shape needed. Soup's current templates treat them as two test suites; it needs a `just test:e2e` that brings up the stack via compose, runs a smoke-test script, and tears down.
7. **Multi-session memory across runs.** Four handoff files in one repo is a symptom: Soup's per-run artifacts don't compose into a project-level history. The `dream-consolidated` memory mentioned in `CLAUDE.md` is aspirational; no implementation found in the layout.
8. **Cost/duration estimates in plans.** The warhammer master plan gives duration-per-agent ("45min", "3-4hrs") and implicit budget. Soup's `ExecutionPlan.budget_sec` is a single whole-plan cap with no per-step hint. Meta-prompter should emit estimated minutes and model cost per step.

---

## Proposed soup additions

1. **`docs/runbooks/` directory with known-failure recipes.** Seed with `python313-pkgutil.md`, `pandas-c-extension.md`, `alembic-postgres-array-on-sqlite.md`, `pydantic-v1-to-v2.md`, `node-18-vs-20.md`. Session-start hook greps user's last error against runbook titles and surfaces links. Direct port of the `PYTHON313_FIX.md` pattern. **Highest steal-value.**
2. **`agent: full-stack-integrator`.** New role with `files_allowed: ["frontend/src/services/**", "frontend/src/types/**", "backend/app/api/**", "backend/app/schemas/**"]`. Owns the OpenAPI ↔ TypeScript contract. Invoked when a TaskStep's file scope spans frontend + backend. Addresses Scenario B's gap.
3. **`skill: contract-drift-detection`.** Procedural gate invoked post-backend-change. Runs `python scripts/check_openapi_drift.py` (new, shipped in template) + `npm run generate:types` + git diff. Fails the TaskStep if drift detected without frontend update.
4. **`.soup/status.md` auto-rollup.** Stop hook regenerates a single markdown file: in-flight runs, last 5 completed runs, open blockers, mtime of each spec, phase badges. Replaces the 4-file handoff tax.
5. **`just ingest-plans <glob>`.** Parse `AGENT_*_SPEC.md`, `*_PLAN.md`, `*_HANDOFF.md` files — phase headers, "depends on" language, duration hints — into a skeleton `ExecutionPlan` JSON for human review. Onboarding lever for brownfield repos.
6. **Per-TaskStep duration + cost hints.** Add `estimated_sec: int | None` and `estimated_tokens: int | None` to `TaskStep`. Meta-prompter populates; orchestrator compares actual vs estimate and logs drift to `experiments.tsv`.
7. **Markdown preview of ExecutionPlan.** `just plan "<goal>"` emits `*.json` + `*.md` side by side. The `.md` mirrors the warhammer "Agent Quick Reference" table. `just show-plan <file>` renders in terminal.
8. **`docker-compose.dev.yml` in `fullstack-python-react` template.** Runs backend (uvicorn --reload), frontend (vite --host 0.0.0.0), postgres, redis. `just dev` brings it up; `just dev-down` stops. Mirrors warhammer's `concurrently` pattern but containerised.
9. **`tests/e2e/` convention in templates.** Root-level pytest+playwright wrapper that shells `docker compose up -d`, awaits health, runs smoke, tears down. Hard-wired to `just test:e2e`.
10. **Debug script TTL directory.** `.soup/debug/<run-id>/` is allowed for `systematic-debugging`-skill subagents. Auto-pruned after 14 days. Legitimises the reproduction scripts without polluting main source tree.

---

## Summary for parent

**Path:** `C:\Users\ethan\AIEngineering\soup\docs\real-world-dogfood\warhammer-40k-calculator.md`

**Top 3 concrete soup additions:**
1. `docs/runbooks/` directory (starting with `python313-pkgutil.md` salvaged from this repo's `PYTHON313_FIX.md`) + session-start hook that surfaces runbook links on known error patterns. Biggest immediate steal.
2. `full-stack-integrator` agent + `contract-drift-detection` skill. Fixes Soup's blind spot for OpenAPI ↔ TypeScript drift — Scenario B showed Soup's subagent isolation actively hurts cross-stack bugs today.
3. `just ingest-plans <glob>` converter that turns prose `AGENT_*_SPEC.md` / `*_PLAN.md` / `*_HANDOFF.md` into a skeleton `ExecutionPlan` JSON. Onboarding brownfield repos onto Soup is currently manual rewrite work.

**Critical learning:** This repo ran a document-driven multi-agent pipeline in 2025 without any of Soup's machinery — and the failure modes it hit (status drift across 4 handoff files, debug scripts multiplying, self-reported completion, Python 3.13 dependency thrash) are exactly what Soup's hooks/schemas/fresh-context design addresses. But the repo solved one thing Soup still hasn't: **project-specific agent briefs that carry domain knowledge**. Soup's roster agents are stack specialists with no project context; real work needs spec-snippet injection into `TaskStep.prompt`. Without that, Soup's prompts will keep being too thin for meaty tasks.
