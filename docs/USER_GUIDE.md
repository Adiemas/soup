# Soup — User Guide

Soup is Streck's opinionated Claude Code framework for building internal apps through a spec-driven pipeline of procedural gates, fresh-context subagents, and automatic QA. This guide walks a Streck engineer from a first `just init` to a deployed internal app — greenfield, brownfield, and everything between.

---

## Who this is for

**You:** a Streck engineer who has been handed a ticket ("build X for Lab Ops") and expected to ship it as an internal app. You know Python or C# or React well enough to read and edit what an agent produces, but you do not want to hand-author the whole thing. You care about QA, reviewability, and not shipping a silent regression.

**You should already know:**
- Enough git to read a PR diff, approve, merge.
- The iron laws in [`CLAUDE.md`](../CLAUDE.md) and [`CONSTITUTION.md`](../CONSTITUTION.md) — soup enforces them mechanically, but you still need to know why.
- Your own stack well enough to recognize a bad abstraction in a diff.
- Bash (Git Bash on Windows) — every recipe in the `justfile` runs under it.

**What soup handles for you:**
- Decomposing a natural-language goal into a validated `ExecutionPlan` DAG.
- Running waves of fresh Claude Code subagents with worktree isolation, atomic commits, and the Stop-hook QA gate.
- Injecting the right stack rules (`rules/python/`, `rules/dotnet/`, etc.) per file being edited.
- Routing compliance obligations (`pii`, `phi`, `lab-data`, `financial`) automatically to affected subagents.
- Citing every RAG-retrieved claim with `[source:path#span]` attribution.
- A three-mode CLI: `just plan` (dry-run), `just go` (supervised), `just go-i` (interactive HITL).

**What soup does NOT do:**
- Think for you on the spec. You still write (or review) "what" and "outcomes."
- Merge to `main` without a human approving the PR — QA `APPROVE` produces a PR; a human still clicks.
- Replace the reviewer. `/review` adds agents, not expertise.
- Work on customer-facing critical-path systems today. Scope is internal apps with low blast radius.

---

## 5-minute quickstart

Clone, init, and run the canonical hello-world. All paths absolute to avoid `cd` confusion:

```bash
# 1. Clone (adjust to your fork/mirror)
git clone https://github.com/streck/soup.git C:/dev/soup
cd /c/dev/soup

# 2. Bootstrap (venv, deps, Postgres via docker, git hooks, .env stub)
just init

# 3. Paste your API key
$EDITOR .env          # set ANTHROPIC_API_KEY (required) + OPENAI_API_KEY (for RAG embeddings)

# 4. Confirm the machine is healthy
just doctor

# 5. Ship something trivial
just go "build me a /health endpoint with a liveness probe"
```

Expected:

```
[meta-prompter/opus] decomposing goal → ExecutionPlan
  steps:
    S1  spec-writer    → specs/health-2026-04-14.md
    S2  plan-writer    → .soup/plans/health.md
    S3  tasks-writer   → .soup/plans/health.json
    S4  test-engineer  → tests/test_health.py       (RED)
    S5  python-dev     → app/routes/health.py       (GREEN)
    S6  verifier       → pytest -q                  PASS
[stop] qa-orchestrator → APPROVE
[pr]   gh pr create → #231 opened
```

Typical wall-clock: 2-8 minutes for a task this small. Cost: ~$0.05-$0.20 per run against Anthropic. Both land in `logging/experiments.tsv`.

If anything goes sideways, `just logs` tails the most recent session JSONL and `just last-qa` prints the QA report.

**Windows note.** Every `just` recipe runs under Git Bash (`set shell := ["bash", "-cu"]`). Read [`../README.md` § Windows setup](../README.md#windows-setup) before the first `just init` — you need Git Bash on `PATH`, Docker Desktop on WSL 2, and `winget install Casey.Just`.

---

## The canonical flow

```
/intake   ──►  /specify  ──►  /clarify  ──►  /plan  ──►  /tasks  ──►  /implement  ──►  /verify  ──►  /deploy
 (new app)     (free-text)    (HITL)         (arch)       (TDD DAG)     (orchestrator)   (QA gate)   (ship)
    │                                                                                                   ▲
    └────────────────── /intake --brownfield <repo> ───────────────── (researcher pre-pass) ────────────┤
                                                                                                        │
          /quick "<ask>"  ───────────►  (test-engineer → implementer) ──────────────────►  (Stop-hook QA)
          (trivial only, ≤20 LOC)       — skips /specify and /plan —                                    │
                                                                                                        │
                                                                            BLOCK  ──► /verify (loop) ──┘
                                                                          APPROVE ──► gh pr create
```

**Narration.**

1. **`/intake`** — structured YAML form → `specs/<slug>-<date>.md`. Primary entry point for brand-new internal apps. For free-text ideas on an existing app, skip to `/specify`. `--brownfield <repo-path>` adds a researcher pre-pass over an existing repo.
2. **`/specify`** — free-text goal → spec. Skipped automatically when `/intake` was run; `spec-writer` is invoked in a different mode from each. `--extends <parent-spec>` augments an already-frozen spec with a delta.
3. **`/clarify`** — walks through `## Open questions` interactively. No guessing. Amends the spec in place. Skipped if there are no open questions.
4. **`/plan`** — `architect` (opus) + `plan-writer` (sonnet) produce `.soup/plans/<slug>.md`. Markdown only; tech choices + file map + risks. Reads the stashed intake YAML for stack/deployment/compliance when present.
5. **`/tasks`** — `tasks-writer` (sonnet) converts the markdown plan into `ExecutionPlan` JSON at `.soup/plans/<slug>.json`. TDD-shaped: every impl step is preceded by a failing-test step. Validated against `schemas/execution_plan.py`.
6. **`/implement`** — `orchestrator` (opus) runs the JSON plan. Waves of fresh subagents in `.soup/worktrees/<slug>/`, atomic commits per step, `verify_cmd` per step, fix-cycle (`verifier` sonnet) on failure up to 3 attempts.
7. **`/verify`** — `qa-orchestrator` dispatches `code-reviewer` + `security-scanner` + `verifier` in parallel → `QAReport` with verdict `APPROVE | NEEDS_ATTENTION | BLOCK`.
8. **`/deploy`** — only after `APPROVE`. `deployer` reads the stashed intake YAML's `deployment_target`, loads the matching `rules/deploy/<target>.md`, runs the post-deploy smoke test + optional `deploy_baseline_cmd`, emits `DeployReport`.

`/quick` is the narrow path for ≤20 LOC one-file changes. It still runs TDD (`test-engineer` writes a failing test; `implementer` makes it pass), and still triggers the Stop-hook QA gate. It skips `/specify` and `/plan`. Anything bigger or cross-cutting `bounce`s back to the full flow (see [`.claude/commands/quick.md`](../.claude/commands/quick.md)).

See [`docs/DESIGN.md` § 4](DESIGN.md#4-flow--canonical-implement-run) for the full narrated flow diagram. See [`docs/ARCHITECTURE.md` § 2](ARCHITECTURE.md#2-data-flow--a-full-implement-run) for what happens inside the orchestrator.

---

## Greenfield — starting from an intake form

The intake form is soup's preferred entry point for new internal apps. It removes one `/clarify` round-trip, pre-populates `## Integrations` in the spec, and threads each integration into downstream `TaskStep.context_excerpts` so specialist subagents see the contract excerpt without re-discovering it.

### What's an intake form

A YAML document validated by [`schemas/intake_form.py::IntakeForm`](../schemas/intake_form.py). See [`intake/README.md`](../intake/README.md) for the full field reference. Highlights:

| Field | Shape | Notes |
|---|---|---|
| `app_slug` | kebab-case | Drives `specs/<slug>-...`, `.soup/plans/<slug>...`, new-repo dir |
| `description`, `intent` | prose | Elevator pitch + the "why" |
| `primary_users` | list[str] | Personas → `## Stakeholders & personas` in the spec |
| `inputs`, `outputs` | list[IntakeField] | `{name, description, type}`; each becomes an EARS REQ |
| `integrations[]` | list[Integration] | `{kind, ref, purpose, auth}` per external system |
| `stack_preference` | enum | `python-fastapi-postgres` / `dotnet-webapi-postgres` / `react-ts-vite` / `fullstack-python-react` / `nextjs-app-router` / `ts-node-script` / `no-preference` |
| `deployment_target` | enum | `internal-docker` / `azure` / `vercel` / `on-prem` / `tbd` |
| `success_outcomes` | list[str] | Testable. E.g. "P95 export <= 5s" — verbatim to `## Acceptance criteria` |
| `constraints` | list[str] | Regulatory / performance / budget — `## Non-functional requirements` |
| `compliance_flags` | list[enum] | `pii` / `phi` / `financial` / `lab-data` / `public` / `internal-only` — drives rule injection |
| `deploy_baseline_cmd` | str? | Optional. Run pre- and post-deploy; regression blocks merge |

Validators reject: non-kebab slugs, non-ISO deadlines, duplicate flags, and mutually exclusive combinations (`public` ⊥ `pii`/`phi`/`financial`/`internal-only`; `internal-only` + `vercel`; `phi` + `vercel`). Run `python -c "from schemas.intake_form import IntakeForm; IntakeForm.from_yaml('intake/<your-app>.yaml')"` to catch errors before `/intake`.

### Worked example — Asset Inventory Lite

Start with [`intake/examples/asset-inventory-lite.yaml`](../intake/examples/asset-inventory-lite.yaml): 1 `github-repo` integration, 1 `database`, `fullstack-python-react`, `internal-docker`, `internal-only`. Lab Ops wants one source of truth for asset locations.

```bash
# 1. Validate the form (cheap — no API calls)
python -c "from schemas.intake_form import IntakeForm; \
           IntakeForm.from_yaml('intake/examples/asset-inventory-lite.yaml')"

# 2. Kick off the flow
/intake --file intake/examples/asset-inventory-lite.yaml
```

The `/intake` command (see [`.claude/commands/intake.md`](../.claude/commands/intake.md)) does:

1. `IntakeForm.from_yaml(path)` — abort on any validation error.
2. Auto-prompt for `--brownfield` if any `github-repo`/`ado-project` integration looks like a local repo. Accept or decline.
3. Collision check: abort if `specs/<app_slug>-<YYYY-MM-DD>.md` already exists (Constitution I.4 — specs are frozen; next version uses `/specify --extends`).
4. Dispatch `spec-writer` in **Mode B** (structured form). Field-to-section map:

   | Intake field | Spec section |
   |---|---|
   | `description` | `## Summary` |
   | `intent` | `## Summary` + `## User outcomes` |
   | `primary_users` | `## Stakeholders & personas` |
   | `inputs` + `outputs` | `## Functional requirements` (one EARS REQ per field) |
   | `success_outcomes` | `## Acceptance criteria` (verbatim — must be testable) |
   | `constraints` | `## Non-functional requirements` |
   | `compliance_flags` | `## Non-functional requirements` + top-of-spec banner |
   | `integrations` | `## Integrations` — one `### <kind>: <ref>` subsection per integration |
   | `deadline` | `## Out of scope` (anything that can't fit) |
   | `stack_preference` / `deployment_target` | **NOT** in the spec — passed forward via stashed YAML only |

5. Save spec to `specs/asset-inventory-lite-2026-04-14.md`.
6. Stash intake in **three** locations by design:
   - `intake/asset-inventory-lite.yaml` — editable human source; reviewed in PRs.
   - `specs/asset-inventory-lite-2026-04-14.intake.yaml` — frozen audit trail travelling with the dated spec.
   - `.soup/intake/active.yaml` — hook-readable pointer; replaced on every `/intake`.
7. Route to next step: `/plan` (fewer than 3 integrations here).

Then:

```bash
/plan
# → .soup/plans/asset-inventory-lite.md
```

`/plan` reads `specs/asset-inventory-lite-2026-04-14.intake.yaml` and passes `stack_preference`, `deployment_target`, `compliance_flags[]`, `integrations[]` as **structured inputs** to the `architect` prompt. Architect produces design + tech choices; `plan-writer` produces the markdown plan with required sections `## Spec`, `## Constitution ref`, `## Overview`, `## Architecture`, `## Tech choices`, `## File map`, `## Risks & mitigations`, `## Task outline`, `## Budget`.

```bash
/tasks
# → .soup/plans/asset-inventory-lite.json (ExecutionPlan)
```

`tasks-writer` emits the TDD-shaped JSON. For every impl task T, two steps:

1. `test-<T>` — `test-engineer`; `verify_cmd` begins with `!` (bash negation) so a failing test exits 0 (see [`docs/PATTERNS.md § 0b`](PATTERNS.md#0b-tdd-red-phase-verify_cmd--canonical-pattern)).
2. `impl-<T>` — specialist (`python-dev`, `react-dev`, etc.); `depends_on: ["test-<T>"]`; `verify_cmd` runs the test expecting GREEN.

Each step declares `files_allowed` (gitignore-style globs — see [`docs/PATTERNS.md § 0c`](PATTERNS.md#0c-files_allowed-glob-dialect)), `model`, `max_turns <= 10`, `parallel` where deps allow. Validated via `soup plan-validate .soup/plans/asset-inventory-lite.json` (or `just plan-validate`).

```bash
/implement
# → .soup/runs/<run_id>/ + atomic commits in .soup/worktrees/asset-inventory-lite/
```

The `orchestrator` (opus) checks out a git worktree at `.soup/worktrees/asset-inventory-lite/`, computes wave topology from `depends_on`, spawns fresh subagents per step. Each subagent sees only `files_allowed`, its `step.prompt`, any resolved `context_excerpts` / `spec_refs`, and the auto-injected rules. `verify_cmd` runs after every step; pass → atomic commit; fail → dispatch `verifier` (fix-cycle) with `systematic-debugging` context; 3 fails → escalate to architect.

```bash
/verify
# → .soup/runs/<run_id>/qa_report.json with verdict APPROVE|NEEDS_ATTENTION|BLOCK
```

If `APPROVE`: `gh pr create` → reviewer(s) merge.

```bash
/deploy
# → .soup/deploy/<run_id>/report.json
```

### Stashed artifacts — what lands where

A greenfield flow deposits these files on disk; they are the audit trail:

| Path | Writer | Purpose | Lifetime |
|---|---|---|---|
| `intake/<slug>.yaml` | You | Editable intake source; reviewed in PR | Survives across spec versions |
| `specs/<slug>-<date>.md` | `spec-writer` | The frozen spec | Frozen (Constitution I.4) |
| `specs/<slug>-<date>.intake.yaml` | `/intake` | Frozen audit trail next to the spec | Frozen, never mutated |
| `.soup/intake/active.yaml` | `/intake` | Hook-readable pointer to the most-recent intake | Replaced on every `/intake` |
| `.soup/plans/<slug>.md` | `plan-writer` | Markdown plan (arch + tech + file map) | Regenerated per plan version |
| `.soup/plans/<slug>.json` | `tasks-writer` | Validated `ExecutionPlan` | Regenerated per plan version |
| `.soup/runs/<run_id>/trace.jsonl` | orchestrator | Per-step subagent transcript | 30-day rolling (`just clean`) |
| `.soup/runs/<run_id>/qa_report.json` | `stop` hook | QA verdict + findings | Immutable |
| `.soup/baseline/<run_id>/{pre,post,diff}.txt` | orchestrator | Brownfield regression diff | Immutable |
| `.soup/worktrees/<slug>/` | orchestrator | Per-feature git worktree | Until `just worktree-rm <slug>` |
| `logging/agent-runs/session-*.jsonl` | hooks | Per-tool-call event log | 30-day rolling |
| `logging/experiments.tsv` | orchestrator | Append-only cost/duration/verdict | Forever |
| `logging/sessions.tsv` | `stop` hook | Per-session ledger | Forever |

### Compliance flags — what they trigger

Flags on `IntakeForm.compliance_flags[]` flow into `.soup/intake/active.yaml`; `.claude/hooks/subagent_start.py` reads them and appends `rules/compliance/<flag>.md` to every subagent's `additionalContext`.

| Flag | Rule file | Triggers on | Effect |
|---|---|---|---|
| `lab-data` | `rules/compliance/lab-data.md` | CAP/CLIA-adjacent lab workflows | 7-year retention reminder; audit-log REQ forced into spec |
| `pii` | `rules/compliance/pii.md` | Storing/transmitting identifiable personal data | `security-scanner` severity floor lifted to `high` |
| `phi` | `rules/compliance/phi.md` | HIPAA-adjacent protected health information | BAA'd infra required; blocks `vercel` |
| `financial` | `rules/compliance/financial.md` | SOX-adjacent financial data | Audit + reconciliation REQs |
| `public` | — | Routing label | Raises CVE severity floor; mutually exclusive with `pii`/`phi`/`financial`/`internal-only` |
| `internal-only` | — | Routing label | Blocks `vercel` deploy |

See [`rules/compliance/README.md`](../rules/compliance/README.md) for the full table and `.claude/hooks/subagent_start.py::COMPLIANCE_FLAGS_WITH_RULES` for the enforcement allow-list. Adding a new flag is a 6-step diff — see [`docs/PATTERNS.md § 10`](PATTERNS.md#10-add-a-new-compliance-rule).

---

## Brownfield — feature engineering on existing repos

Many Streck repos already have code, tests, specs-as-markdown, and shipped contracts. Editing them blind is how silent regressions ship. Soup's brownfield surface is three levers: researcher pre-pass, spec extension, and baseline capture.

### `/intake --brownfield <repo-path>`

Runs before `spec-writer`. The `researcher` utility agent (haiku, 10-search budget, Read/Grep/Glob only) produces `.soup/research/<slug>-findings.md` — a findings table (`file | line | relevance | excerpt`) over the target repo. The spec-writer reads the findings and references them via `spec_refs`; the spec's `## Brownfield notes` section names the parent repo and the findings path.

```bash
# New feature against an existing Streck repo
/intake --file intake/<feature>.yaml --brownfield /c/dev/combat-calculator
```

The findings file is **load-bearing**, not cosmetic — downstream `tasks-writer` hydrates `context_excerpts` from it. If the researcher returns an empty table, `/intake` aborts; re-run with a scoped `--brownfield <sub-path>`.

### `/specify --extends <parent-spec>`

Augments an already-frozen parent spec under `specs/` with a delta. `spec-writer` reads the parent in full, preserves its frozen requirements (Constitution I.4), and emits a `## Extends` section with a diff-style delta table:

```markdown
| Parent REQ | Relation | Extension REQ | Note |
|---|---|---|---|
| REQ-3 | preserves | — | Byte-for-byte response shape retained. |
| REQ-5 | augments | REQ-E-1 | Adds `distribution` key; existing fields unchanged. |
| REQ-7 | deprecates | — | Marked deprecated; removal horizon: next minor. |
| — | adds | REQ-E-2 | New capability; no parent counterpart. |
```

`Relation` values: `preserves`, `augments`, `deprecates`, `adds`. See [`.claude/commands/specify.md` § Extends mode](../.claude/commands/specify.md) for the full contract.

### `hydrate_context_excerpts.py`

Parses a researcher findings file (markdown table: `file|line|relevance|excerpt`) and writes `<plan>.hydrated.json` with each `TaskStep.context_excerpts` populated from matching findings. Unmatched findings land in the plan's `notes`.

```bash
just hydrate-plan .soup/research/my-feature-findings.md .soup/plans/my-feature.json
# → .soup/plans/my-feature.hydrated.json
```

The hydrated plan is what `/implement` runs. Per-step `context_excerpts` land under `## Context excerpts (verbatim)` in the subagent's first-turn prompt (injected by `orchestrator/agent_factory.py::_compose_brief`), so the subagent doesn't need to re-Read source files.

### `regression_baseline_cmd` — pre/post-run diff

A `TaskStep`-level `verify_cmd` only catches local breakage. The baseline command catches the neighbour it never touches. Set `ExecutionPlan.regression_baseline_cmd` to a bash one-liner that enumerates the "currently passing" surface of the whole app — the orchestrator runs it once pre-S1 and once post-final-wave, writing `pre.txt` / `post.txt` / `diff.txt` under `.soup/baseline/<run_id>/`.

A non-empty diff marks `RunState.status == "regression"` (distinct from `passed`/`failed`/`aborted`). The QA gate attaches the diff as a high-severity finding; the operator decides to merge, review, or block.

See `.claude/skills/brownfield-baseline-capture/SKILL.md` for the 4-phase enumerate → capture → modify → diff loop. Iron law:

> FREEZE WHAT'S ALREADY WORKING BEFORE YOU CHANGE IT. DIFF BEFORE YOU SHIP.

Canonical baseline commands:

- Python: `pytest -q --co -q | sort` (collected test IDs)
- OpenAPI: `curl -s http://localhost:8000/openapi.json | jq -S .`
- DB schema: `pg_dump --schema-only $DATABASE_URL | grep -E '^(CREATE|ALTER)' | sort`

### Relevant rules

- [`rules/global/brownfield.md`](../rules/global/brownfield.md) — iron law: *Read existing code + tests BEFORE proposing changes. Write regression tests BEFORE modifying observed behavior.* Mandatory pre-edit checklist: read file in full → find tests → run baseline → read callers → write characterization test → only then edit. Anti-patterns table. Hook enforcement via `pre_tool_use.py` and `verifier`.
- [`rules/global/deprecation.md`](../rules/global/deprecation.md) — any removal or rename of a public surface must route through a multi-PR deprecation cycle (add replacement → migrate callers → remove old).
- [`rules/global/change-budget.md`](../rules/global/change-budget.md) — size tiers: `/quick` ≤ 20 LOC; normal ≤ 200 LOC; architect pre-pass 200-1000 LOC; split beyond 1000. Breaking changes always route through deprecation.

### Worked example — damage simulator on top of a combat calculator

Goal: add damage-distribution simulation to an existing Streck combat-calculator repo that already exposes `/calculate` returning expected damage.

```bash
# 1. Researcher pre-pass + spec extension (since the parent already has a spec)
/intake --brownfield /c/dev/combat-calculator          # if no parent soup spec
# OR
/specify --extends specs/combat-calculator-2026-02-08.md \
         "Add a damage-distribution simulator that runs 10k Monte Carlo rolls and returns variance + P50/P95/P99 statistics alongside the existing expected-damage response."

# 2. /plan — the architect sees:
#    - parent spec's REQ-3 (expected-damage contract)
#    - researcher findings: /calculate endpoint lives at app/routes/combat.py:L42
#    - compliance: none (internal tool)
/plan

# 3. /tasks — tasks-writer emits RED/GREEN pairs. Because the parent has
#    a passing suite, the plan will carry a regression_baseline_cmd like:
#    "pytest -q --co -q | sort > /dev/stdout"
/tasks
cat .soup/plans/combat-damage-simulator.json | jq .regression_baseline_cmd

# 4. /implement — orchestrator snapshots the baseline before S1,
#    runs the waves, snapshots again after, diffs. Any test ID that
#    was collected pre- but missing post- marks "regression".
/implement

# 5. /verify — QA gate. The diff is attached to QAReport as a finding.
/verify
```

The baseline catches a regression the per-step `verify_cmd` misses: if `tests/test_legacy_calculator.py::test_dragons_vs_lances` was passing pre-run and no longer collected post-run, the diff flags it even though every RED/GREEN pair passed.

---

## Pointing soup at your GitHub code

Soup integrates with GitHub two ways: the `github-agent` for live operations (PRs, issues, checks), and `/rag-ingest github://...` for indexing code and docs into the RAG layer so `rag-researcher` can cite them later.

### `github-agent` — live GitHub operations

Thin wrapper over the `gh` CLI. Defined in [`.claude/agents/github-agent.md`](../.claude/agents/github-agent.md). Used for:

- Opening PRs after `/implement` APPROVEs.
- Reading issues for a `specify` goal ("implement issue #482").
- Fetching a PR's CI check results for a `verifier` retry.
- Materializing a GitHub issue/PR reference (`#482` or `streck/auth-service#482`) into `.soup/research/<slug>/` for `context_excerpts` threading.

Requires `gh auth login` (done once outside soup). For private repos, `GITHUB_TOKEN` on the env with `repo` scope (classic PAT) or `Contents: Read` (fine-grained).

### `/rag-ingest github://...` — index into RAG

```bash
# Default branch of a public repo (anonymous; rate-limited at 60 req/h)
just rag-ingest github://streck/auth-service

# Specific branch
just rag-ingest github://streck/auth-service@release/2026.04

# Private repo (needs GITHUB_TOKEN with `repo` scope)
just rag-ingest github://streck/internal-wiki
```

The GitHub source adapter walks the merged tree (blob content only — no issues, no PRs), chunks every file whose extension is on the allow-list (`.md`, `.py`, `.cs`, `.ts`, `.tsx`, `.sql`, etc.), and writes chunks to LightRAG + Postgres via `rag/ingest.py`. Dedup is client-side via `Chunk.hash()` and server-side via LightRAG's document content hash.

Files >1.5 MB and unsupported extensions are skipped. The adapter does **not** respect `.gitignore` today; rely on the extension allow-list and never check secrets into a repo you plan to ingest.

### How GitHub context flows into TaskSteps

1. `/rag-ingest github://streck/auth-service` — one-time per project.
2. `/plan` or `/tasks` — `rag-researcher` runs the autoresearch loop ([`.claude/skills/agentic-rag-research/SKILL.md`](../.claude/skills/agentic-rag-research/SKILL.md)) to produce findings with `[source:path#span]` citations and an "Excerpts ready for `context_excerpts`" table mapping each cite to a project-relative materialized file under `.soup/research/<plan-slug>/`.
3. `tasks-writer` threads each materialized path into the matching `TaskStep.context_excerpts`.
4. `orchestrator/agent_factory.py::_compose_brief` resolves `context_excerpts` (relative paths, 20 KB caps) + `spec_refs` (40 KB caps) at brief-compose time and appends them verbatim to the subagent's first-turn prompt under `## Context excerpts (verbatim)`.
5. The subagent reads the excerpts in its first turn — no extra `Read` calls.

For the full RAG path, see the next section and [`docs/USER_GUIDE_RAG.md`](USER_GUIDE_RAG.md).

---

## Pulling context from Azure DevOps

Soup's ADO integration is symmetric to GitHub: the `ado-agent` for live operations, `/rag-ingest ado-wiki://...` for wiki content, and `/rag-ingest ado-wi://...` for work items.

### `ado-agent` — live ADO operations

Wraps the `az devops` CLI. Defined in [`.claude/agents/ado-agent.md`](../.claude/agents/ado-agent.md). Used for work items, repos, and pipelines. Env:

```bash
ADO_ORG=streck                    # https://dev.azure.com/streck
ADO_PROJECT=Platform              # default project
ADO_PAT=...                       # PAT with Read on Wiki + Work Items (minimum)
```

For write ops (commits, PR updates, pipeline runs), the PAT needs `Code (Read & write)`, `Pipelines (Read & execute)`, `Work Items (Read & write)`.

### `/rag-ingest ado-wiki://<org>/<project>/<wiki>`

```bash
# Discover wiki ID automatically (picks values[0] — fine for single-wiki projects)
just rag-ingest ado://streck/Security

# Pin a specific wiki by id or name
just rag-ingest ado://streck/Security/Security.wiki
```

The adapter lists pages with `recursionLevel=full`, fetches each with `includeContent=true`, and chunks the markdown. `source_path` preserves the hierarchy so citations point straight to the page:

```
[source:ado://streck/Security/Security.wiki/AuthFlow.md#10-44]
```

Caveats: code wikis (with versionDescriptors) are not distinguished today — ingest only project wikis until the adapter fix lands. Attachments are dropped. No incremental updates — each re-ingest re-fetches. Wikis with >5k pages can time out.

### `/rag-ingest ado-wi://<org>/<project>/<id|wiql>`

```bash
# Single work item
just rag-ingest "ado-wi://streck/Platform/482"

# Filter clause (adapter wraps as WIQL)
just rag-ingest "ado-wi://streck/Platform/[System.AssignedTo] = @Me AND [System.State] = 'Active'"

# Full WIQL pastes untouched
just rag-ingest "ado-wi://streck/Platform/SELECT [System.Id] FROM WorkItems WHERE [System.Tags] CONTAINS 'auth'"
```

Each work item materializes as:

```markdown
# <Type> <id>: <title>
- **State:** <state>
- **Type:** <type>
- **Assigned to:** <displayName>
## Description
<System.Description, rendered markdown>
## Acceptance criteria
<Microsoft.VSTS.Common.AcceptanceCriteria>
## Comments
### <author> — <timestamp>
<comment body>
```

Citations land like:

```
[source:ado-wi://streck/Platform/482#wi-482#acceptance-criteria]
```

With no `ADO_PAT`, the adapter returns zero chunks (stub-safe; no crash).

### Auto-resolution of `STRECK-<n>` / `ADO-<n>` references

When a spec, plan, or intake form references `STRECK-<n>` or `ADO-<n>` and the env has `ADO_PAT`, `ADO_ORG`, `ADO_PROJECT` set, `spec-writer` and `architect` auto-populate `spec_refs` with the corresponding `ado-wi://<org>/<project>/<id>` URI. The `ado-agent` fetches the work item via `AdoWorkItemsSource` and writes `.soup/research/<plan-slug>/wi-<n>.md` for downstream `context_excerpts` threading.

If the env is unconfigured, soup logs a friendly hint and leaves the ref unresolved; a future run materializes it when the env catches up.

---

## RAG setup (quick)

Full walkthrough lives in [`docs/USER_GUIDE_RAG.md`](USER_GUIDE_RAG.md). Condensed steps:

```bash
# 1. Required env in .env
ANTHROPIC_API_KEY=sk-ant-...      # meta-prompter + every subagent
OPENAI_API_KEY=sk-...             # LightRAG embeddings (1536-dim)
POSTGRES_URL=postgres://soup:soup@localhost:5432/soup_rag
GITHUB_TOKEN=ghp_...              # private GitHub repos
ADO_PAT=...                       # ADO wikis + work items

# 2. Postgres + pgvector (docker-compose runs this automatically on `just init`)
docker compose -f docker/docker-compose.yml up -d postgres

# 3. Sanity check — Postgres reachable? embeddings key set? lightrag-hku importable?
just rag-health

# 4. Ingest sources
just rag-ingest github://streck/auth-service
just rag-ingest ado://streck/Security
just rag-ingest "ado-wi://streck/Platform/482"

# 5. Query
just rag "how does AuthService validate JWTs?"

# 6. Expose to Claude Desktop / other MCP clients
just rag-mcp           # stdio server; wire into .claude/settings.json mcpServers
```

Every retrieval includes `[source:path#span]` citations. Agents preserve them verbatim — uncited RAG-derived claims are flagged by `code-reviewer` as a high-severity finding (Constitution VII.3).

Read [`docs/USER_GUIDE_RAG.md`](USER_GUIDE_RAG.md) for: PAT scopes, adapter caveats, ingest cost estimates, MCP server wiring, and the end-to-end ingest → research → `context_excerpts` flow.

---

## Deploying

`/deploy` closes the intake → implement → verify → deploy loop. It never skips the QA gate; running without a recent `APPROVE` verdict aborts.

### The command

```bash
/deploy                              # reads deployment_target from stashed intake
/deploy --target azure               # override; requires non-empty reason, logged on report
```

See [`.claude/commands/deploy.md`](../.claude/commands/deploy.md) for the full workflow.

### Flow

1. **Gate on QA.** Find the most recent `qa_report.json` under `.soup/runs/<run_id>/`. If `verdict != "APPROVE"`, abort + print report path.
2. **Gate on intake.** Read `.soup/intake/active.yaml` via `IntakeForm.from_yaml`. Missing or invalid → abort.
3. **Resolve target.** `--target <override>` wins; else `form.deployment_target`. If `tbd` and no override, abort.
4. **Dispatch `deployer`** (sonnet). Reads the target, loads `rules/deploy/<target>.md` + `rules/deploy/secrets.md`, renders/edits CI config only. `files_allowed`: `Dockerfile*`, `.github/workflows/**`, `azure-pipelines.yml`, `vercel.json`, `docker-compose*.yml`, `deploy/**`. Never touches app code.
5. **Smoke test + baseline.** Deployer hits the target's health endpoint and, if `deploy_baseline_cmd` is set on the intake, runs it pre- and post-deploy; diffs attach to the report.
6. **`DeployReport`** — JSON under `.soup/deploy/<run_id>/report.json` with verdict `deployed | refused | rolled-back | regression`.

### Targets and injected rules

Each target has a rule file under `rules/deploy/` the deployer loads:

| Target | Rule file | Use when |
|---|---|---|
| `internal-docker` | `rules/deploy/internal-docker.md` | VPN-only internal apps; compose + systemd on `docker-host-01.internal.streck`. Natural home for `internal-only`, `lab-data`. |
| `azure` | `rules/deploy/azure-app-service.md` | Public-or-VNet ingress on Azure App Service; slot-based blue/green. Supports `pii`/`phi`/`financial` (BAA on commercial). |
| `vercel` | `rules/deploy/vercel.md` | Public-edge SaaS (typically `nextjs-app-router`). Refuses `internal-only` + `phi`. |
| `on-prem` | (via `rules/deploy/internal-docker.md`) | Existing on-prem host; treated as a variant of internal-docker today. |
| `tbd` | — | Placeholder; `/deploy` aborts with hint "re-run /intake or pass --target". |

Cross-cutting rules:

- `rules/deploy/secrets.md` — auto-loaded alongside the target-specific rule. Never read secrets from `.env`; CI injects them from the deploy host or OIDC.
- `rules/deploy/github-actions.md` / `rules/deploy/ado-pipelines.md` — pipeline authoring conventions by CI provider.

### Intake validator — fail fast

The `IntakeForm._flags_are_consistent` validator rejects common mis-deploys at form time, not deploy time:

- `internal-only` + `vercel` → `ValueError("Vercel is public-edge; use on-prem or azure for internal-only")`.
- `phi` + `vercel` → `ValueError("PHI requires BAA'd infra; Vercel doesn't sign BAAs by default")`.
- `public` + any of `internal-only`/`pii`/`phi`/`financial` → rejected.
- `tbd` without a `constraints` entry mentioning "deploy TBD" → advisory warning.

The deployer re-checks at deploy time (belt-and-suspenders) in case an older pre-validator intake slipped through.

### `deploy_baseline_cmd`

Symmetrical to `ExecutionPlan.regression_baseline_cmd` but run against the **deployed target**, not the local worktree. Example for `internal-docker`:

```bash
deploy_baseline_cmd: >
  curl --cacert /etc/ssl/streck-internal-ca.pem
       -fsS https://asset-inventory.internal.streck/api/status
       | jq -S .
```

Any diff between the pre-deploy and post-deploy baseline → `DeployReport.verdict == "regression"`; the rollback mechanism fires (previous-image-tag rollback for internal-docker, slot swap for Azure, previous-promotion for Vercel).

---

## Observability + incident response

Every soup-built app gets structured logging, correlation IDs, and health/ready/version endpoints wired by default. Every soup *run* emits JSONL telemetry that is queryable from the CLI.

### App-side wiring (shipped in templates)

- **`rules/observability/*.md`** — six rule files routed by `pre_tool_use.py` to entry-point files (`**/main.py`, `**/Program.cs`, `**/app/**/route.ts`, `**/src/middleware.ts`). Cover: structured logging, correlation IDs, health/ready/version, error tracking, metrics.
- **Python FastAPI template** — `structlog` + correlation-id middleware + `/health`, `/ready`, `/version` endpoints already in `app/main.py`. Drop your domain logic on top.
- **Next.js App Router template** — `/api/ready`, `/api/version` routes + `x-request-id` middleware shipped.
- **Other templates** — CLAUDE.md pointer to `rules/observability/README.md`; wire it up as you add your first endpoint.

The rule conventions:

- **Event names:** `{Domain}.{Action}_{State}` (e.g. `Payment.Refund_started`, `Payment.Refund_failed`). Defined once in `rules/global/logging.md`, extended for app-side in `rules/observability/structured-logging.md`.
- **Correlation IDs:** generated at the edge (HTTP middleware or job dispatcher), propagated through `X-Request-Id` header + log context + downstream API calls + DB query tags.
- **Level guidance:** `INFO` for state transitions, `WARN` for degraded/fallback paths, `ERROR` only when someone has to act.
- **Cardinality:** no PII in tags/labels, ever.

### Run-side telemetry (soup itself)

Every orchestrator run writes:

- `logging/agent-runs/session-<id>.jsonl` — per-subagent structured log (tool calls, agent name, parent/root/wave/step fields for tree reconstruction).
- `logging/experiments.tsv` — one row per wave with `run_id`, `agent`, `model`, tokens, `cost_usd`, verdict. Orchestrator-owned.
- `logging/sessions.tsv` — one row per Stop-hook session with files touched + verdict placeholder. Stop-hook-owned. Schema separated from `experiments.tsv` deliberately (v1 comment header: `# soup-schema:sessions-v1`).
- `logging/baseline-<run_id>.jsonl` — pre/post baseline capture (if `regression_baseline_cmd` set on the plan).

### Querying logs — `soup logs`

```
soup logs tail [--session <id>] [--lines 50] [--follow]
soup logs tree <run_id>
soup logs search "<query>" [--session <id>] [--agent <name>]
```

- `tail` — last N lines of the latest or named session.
- `tree` — reconstructs parent → child → grandchild subagent tree from `parent_session_id` / `root_run_id` / `wave_idx` / `step_id` fields. Shows agent name, step id, duration inline.
- `search` — grep structured JSONL for matching events; filters by session or agent.

Justfile shortcuts: `just logs`, `just logs-tree <run-id>`, `just logs-search "<query>"`.

### Cost accounting — `soup cost-report`

```
soup cost-report [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--group-by agent|plan|model]
```

Aggregates the `cost_usd` column from `experiments.tsv`. Rate card (internal estimate): opus $15/$75 per MTok in/out, sonnet $3/$15, haiku $1/$5. Groups by agent name by default.

Justfile shortcut: `just cost-report` (defaults to group-by-agent).

### Incident response

Separately from `docs/runbooks/*.md` (known failures with documented fixes), novel incidents get their own flow:

- **`incident-responder` agent** (sonnet, read-only on prod). Invoked for a new incident report; traces symptom → log events (via `soup logs search`) → code (via Grep) → proposes repro case → spawns `test-engineer` for a regression test → drafts postmortem.
- **`docs/incidents/TEMPLATE.md`** — canonical postmortem format (summary, impact, timeline, root cause, contributing factors, what went well, action items, references).
- **`docs/incidents/README.md`** — the distinction between runbooks (known issues) and incidents (novel), plus when to escalate.

Hard block: `incident-responder` never writes to production; its output is always a postmortem markdown + a proposed fix diff for a human to apply.

---

## justfile cheat-sheet

Every recipe below runs under `bash -cu` (Git Bash on Windows). Recipes with arguments quote them: `just go "<goal>"`.

| Recipe | One-line purpose |
|---|---|
| `just` (or `just help`) | List every available recipe with summary |
| `just init` | Bootstrap: venv, deps, Postgres, .env stub, hooks; idempotent |
| `just install` | Register Claude Code hooks from `.claude/settings.json` |
| `just install-hooks` | Point `core.hooksPath` at `.githooks/` (secret-scan pre-commit) |
| `just plan "<goal>"` | Deterministic: meta-prompter dry-run; writes `.soup/plans/<ts>.json` only |
| `just go "<goal>"` | Supervised: plan + orchestrator.run + auto-verify (default path) |
| `just go-i "<goal>"` | Interactive: plan + HITL `AskUserQuestion` at each wave boundary |
| `just quick "<ask>"` | Single-file, <=20 LOC change; runs `test-engineer` + `implementer` |
| `just rag "<query>"` | Query the RAG index; returns hits + `[source:path#span]` citations |
| `just rag-ingest "<uri>"` | Add a source — `github://`, `ado://`, `ado-wi://`, `file:///`, `https://` |
| `just rag-mcp` | Start MCP server (stdio) so Claude Desktop / other clients can query |
| `just rag-health` | Postgres reachable? `OPENAI_API_KEY` set? `lightrag-hku` importable? |
| `just rag-reindex` | Re-ingest every known source (idempotent) |
| `just hydrate-plan <findings> <plan>` | Populate `context_excerpts` from a researcher findings file |
| `just verify` | Run `qa-orchestrator` on HEAD (no side effects outside logging) |
| `just verify-run <run-id>` | Replay QA gate against a specific `.soup/runs/<id>` dir |
| `just plan-validate <path>` | Validate a plan JSON against the schema + library roster |
| `just ingest-plans "<glob>"` | Convert prose `*_SPEC.md`/`*_PLAN.md` into `ExecutionPlan` skeletons for review |
| `just new <template> <name>` | Scaffold a new internal app from `templates/<template>/` |
| `just templates` | List available stack templates |
| `just worktree <name>` | Create an isolated worktree under `.soup/worktrees/<name>` |
| `just worktree-rm <name>` | Remove a worktree cleanly |
| `just preset <name>` | Copy `.claude/settings.presets/<name>.json` over `settings.local.json` |
| `just logs` | Tail the most recent session JSONL |
| `just logs-tree <run-id>` | Reconstruct parent→child subagent tree for a run |
| `just logs-search "<query>"` | Grep structured session logs for matching events |
| `just experiments` | Open `logging/experiments.tsv` as a rich table |
| `just cost-report [group_by]` | Aggregate `cost_usd` (by agent / plan / model) |
| `just last-qa` | Pretty-print the last QA report |
| `just test` | Framework self-tests (`pytest -q`) |
| `just lint` | `ruff check .` — same as CI |
| `just typecheck` | `mypy .` — same as CI |
| `just fmt` | `ruff format .` |
| `just ci` | `lint` + `typecheck` + `test` — full local CI |
| `just clean` | Remove `.soup/runs` older than 30d; plans + memory preserved |
| `just clean-all` | Nuke caches (`.venv`, `__pycache__`, etc.); keep `.env`, `.soup/memory` |
| `just doctor` | Print repo + env health summary for bug reports |

---

## Command cheat-sheet

Slash commands live in `.claude/commands/`. Invoke from inside a Claude Code session. Each command has a matching agent or agent-chain in `library.yaml`. Grouped by flow stage.

**Project bootstrapping.**

| Command | One-line purpose |
|---|---|
| `/install` | Bootstrap the project — venv, deps, Postgres, hooks, MCP (three modes: default / supervised / `hil`) |
| `/constitution [view\|edit\|bump]` | View or amend `CONSTITUTION.md`; every edit invalidates in-flight plans |
| `/soup-init <template> <name>` | Scaffold a new internal app in a sibling directory from `templates/<template>/` |
| `/map-codebase [root]` | Pre-planning survey; writes `docs/codebase-map.md` |

**Spec / plan authoring.**

| Command | One-line purpose |
|---|---|
| `/intake [--file <yaml>] [--brownfield <repo>]` | Validate intake YAML + optional researcher pre-pass → spec |
| `/specify "<goal>" [--extends <parent-spec>]` | Free-text goal → spec in EARS format; `--extends` augments a frozen parent |
| `/clarify [spec-path]` | Resolve `## Open questions` via interactive HITL prompts |
| `/plan [spec-path]` | `architect` + `plan-writer` → `.soup/plans/<slug>.md` (markdown only) |
| `/tasks [plan-path]` | `tasks-writer` → `.soup/plans/<slug>.json` (validated `ExecutionPlan`) |
| `/ingest-plans "<glob>"` | Convert prose agent/plan/handoff files into `ExecutionPlan` JSON skeletons |

**Execution.**

| Command | One-line purpose |
|---|---|
| `/implement [plan-json]` | Run orchestrator — waves, worktree, atomic commits, Stop-hook QA |
| `/quick "<ask>"` | Ad-hoc two-step (test-engineer + implementer) for <=20 LOC changes |

**QA / review.**

| Command | One-line purpose |
|---|---|
| `/verify` | `qa-orchestrator` → code-reviewer + security-scanner + verifier → `QAReport` |
| `/review [base-ref] [--rounds N]` | Cross-agent peer review; `N >= 2` adds `red-team-critic` + `over-eng-critic` |
| `/deploy [--target <override>]` | Dispatch `deployer` per intake `deployment_target`; requires APPROVE |

**Knowledge.**

| Command | One-line purpose |
|---|---|
| `/rag-search "<query>"` | Query org knowledge; returns synthesis + cited excerpts |
| `/rag-ingest "<uri>"` | Add a GitHub/ADO/filesystem/web source to the RAG index |

---

## Agent roster summary

Full yaml cards in `.claude/agents/*.md`; full roster table in [`.claude/agents/REGISTRY.md`](../.claude/agents/REGISTRY.md). Tiering:

| Tier | Model | Purpose | Examples |
|---|---|---|---|
| **Orchestrator** | `opus` | Planning, decomposition, cross-agent coordination | `orchestrator`, `meta-prompter`, `architect`, `qa-orchestrator` |
| **Specialist** | `sonnet` | Stack-specific implementation; TDD-gated | `implementer`, `python-dev`, `dotnet-dev`, `react-dev`, `ts-dev`, `sql-specialist` (opus for migrations), `full-stack-integrator`, `test-engineer`, `spec-writer`, `plan-writer`, `tasks-writer`, `verifier`, `deployer` |
| **Reviewer** | `sonnet` | Quality / security / correctness gates | `code-reviewer`, `security-scanner` |
| **Critic** | `sonnet` | Round >=2 of `/review` only; read-only | `red-team-critic`, `over-eng-critic` |
| **Utility** | `haiku` | Bounded, read-mostly tasks | `researcher`, `doc-writer`, `docs-scraper`, `git-ops`, `docs-ingester`, `rag-researcher`, `github-agent`, `ado-agent` |

Cost discipline (Constitution VIII): `opus` is reserved for `orchestrator`, `meta-prompter`, `architect`, `sql-specialist` (migrations only). Overriding a tier needs written rationale in the PR body.

Cross-cutting blockers every agent inherits:
- MUST NOT write outside `files_allowed`.
- MUST NOT commit secrets.
- MUST NOT bypass the Stop-hook QA gate.
- MUST NOT force-push to `main`/`master`.
- MUST cite RAG retrievals with `[source:path#span]`.
- MUST escalate after 3 failed fix attempts on the same bug.

---

## Skill primer

Skills are procedural gates — an iron law plus a numbered checklist any agent can load before acting. Agent-invoked, cross-cutting (apply regardless of stack). Full list in [`library.yaml`](../library.yaml). The 5 most-used:

**`tdd`** — Every behavior is driven by a test that fails first. Code ahead of a failing test is deleted. RED (failing test) → GREEN (minimum code) → REFACTOR. Iron law: *NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST. PRE-TEST CODE IS DELETED.* Red flag: "I already wrote the impl; let me add a test to cover it" → delete the impl; start over.

**`systematic-debugging`** — Bugs go through 4 phases before any code change: Investigate → Pattern analysis → Hypothesis → Implementation. Three failed fixes on the same defect escalate to the architect. Iron law: *NO FIX BEFORE A WRITTEN HYPOTHESIS BACKED BY EVIDENCE. 3 FAILED FIXES → ESCALATE.* The hook log records whether you wrote the hypothesis — skipping to "here's my fix" is visible.

**`verification-before-completion`** — Never say "done", "fixed", "passing", or "ready" without running the verification command fresh and quoting real output. Confidence is not evidence. Iron law: *EVIDENCE BEFORE CLAIMS. ALWAYS. QUOTE THE verify_cmd OUTPUT OR DO NOT CLAIM COMPLETION.* Red flag: "tests passed last run, it's fine" → run fresh.

**`spec-driven-development`** — Non-trivial work flows through `/constitution → /specify → /clarify → /plan → /tasks → /implement → /verify`. Each phase has a canonical command, artifact, and gate. Iron law: *SKIP NO PHASE FOR NON-TRIVIAL WORK.* `/quick` is only for genuinely trivial one-liners; anything crossing a contract boundary or >20 LOC disqualifies.

**`brownfield-baseline-capture`** — Iron law: *FREEZE WHAT'S ALREADY WORKING BEFORE YOU CHANGE IT. DIFF BEFORE YOU SHIP.* 4 phases: enumerate the "currently passing" surface → capture pre-S1 → modify in worktree → diff post-final against pre. Pairs with `ExecutionPlan.regression_baseline_cmd`; the orchestrator runs the command at both ends and writes the diff to `.soup/baseline/<run_id>/diff.txt` as a high-severity QA finding on non-empty diff.

Other skills worth knowing (full list in [`library.yaml`](../library.yaml)): `brainstorming`, `writing-plans`, `executing-plans`, `subagent-driven-development`, `dispatching-parallel-agents`, `using-git-worktrees`, `requesting-code-review`, `agentic-rag-research`, `meta-prompting`, `cli-wrapper-authoring`, `contract-drift-detection`.

---

## Templates

Six stack templates under `templates/`. Scaffold with `just new <template> <app-name>` or from inside a Claude Code session with `/soup-init <template> <app-name>`. Each is minimal-but-runnable — `just dev`/`just test` green on the first try. See [`docs/PATTERNS.md § 6`](PATTERNS.md#6-add-a-new-template) for the six required touch-points every template lands.

| Template | When to pick | Notable bits |
|---|---|---|
| `python-fastapi-postgres` | Backend-only service; REST or Typer CLI; needs Postgres | FastAPI + pytest + ruff + mypy strict; sqlc-ready migrations under `migrations/` |
| `dotnet-webapi-postgres` | C# service; existing .NET estate; EF Core + Npgsql | ASP.NET Core 8 + xUnit + nullable reference types enabled; EF migrations |
| `react-ts-vite` | Pure frontend (client-side); internal tool with an existing backend API | React 18+ functional + hooks only; Vite; RTL + Playwright |
| `fullstack-python-react` | Full-stack dashboard: Python API + React SPA + Postgres | Co-located monorepo; `full-stack-integrator` handles OpenAPI ↔ TS type contracts |
| `nextjs-app-router` | Public-edge SaaS or marketing site; SSR/ISR needed | App Router defaults; Server Components + Server Actions; Playwright e2e |
| `ts-node-script` | Scheduled job, cron, one-binary CLI; no backend | Strict tsconfig + esbuild; Zod at all external boundaries |

Each template ships with its own `CLAUDE.md` (stack-specific iron laws), `README.md` (engineer-facing), `justfile` (canonical `init`/`dev`/`build`/`test`/`lint`/`typecheck`), minimal runnable source, and at least one passing test.

---

## Permission presets

`.claude/settings.json` ships a permissive allow-list covering Python, .NET, Node, Postgres, Docker, Playwright, etc. For repos with a narrower surface, named presets under `.claude/settings.presets/<name>.json` copy over `.claude/settings.local.json`:

| Preset | When to use | Bash surface |
|---|---|---|
| `restricted.json` | Pure scripts, one-binary services, cron jobs, code-gen repos — anything that doesn't need a full language runtime | Only `gh auth:*`, `gh repo:*`, `git push:*`, `git status`, `git diff`, `git log` + Read/Grep/Glob/Edit/Write. No python / node / dotnet / docker. |
| `development.json` | Default soup multi-stack feature work (snapshot of the shipped `settings.json`) | Full: python/uv/pip, node/npm/pnpm, dotnet, docker, psql, playwright, etc. |

```bash
just preset restricted        # or: just preset development
# prompts for confirmation before overwriting .claude/settings.local.json
# then: restart Claude Code so settings.local.json is picked up at session start
```

Never commit `.claude/settings.local.json` — per-clone by design; `.gitignore` excludes it. See [`docs/PATTERNS.md § 8b`](PATTERNS.md#8b-permission-presets) for authoring a new preset.

---

## Troubleshooting

**First stop: `just doctor`.** Prints Python environment, docker, Postgres connectivity, hook registration, `.env` load. Exits non-zero on any missing piece.

**Second stop: runbooks.** `docs/runbooks/` is a library of known-failure recipes — each one: Symptom → Cause → Fix → Related. The `session_start` hook scans the directory and surfaces the titles to Claude at session start, so the agent checks a runbook before iterating a fresh diagnosis.

| Runbook | Symptom |
|---|---|
| [`anthropic-rate-limit.md`](runbooks/anthropic-rate-limit.md) | `anthropic.RateLimitError: 429`; Retry-After set — parallel opus burst or ingest storm |
| [`postgres-container-not-ready.md`](runbooks/postgres-container-not-ready.md) | `psycopg.OperationalError: Connection refused` or "database is starting up" — `depends_on` race |
| [`playwright-hydration-flake.md`](runbooks/playwright-hydration-flake.md) | Next.js/RSC tests flake on `'use client'` islands — click before hydration |
| [`python313-pkgutil.md`](runbooks/python313-pkgutil.md) | `AttributeError: module 'pkgutil' has no attribute 'ImpImporter'` — stale setuptools on 3.13 |
| [`npgsql-utc-datetime.md`](runbooks/npgsql-utc-datetime.md) | `DateTime with Kind=Unspecified to timestamp with time zone` — Npgsql 6+ UTC strictness |

Add a runbook via the format in [`docs/runbooks/README.md`](runbooks/README.md) — cap ~2 KB; symptom section greppable.

**Rate-limit / budget exceeded.**

- Check `logging/experiments.tsv` for the cost of the last N runs. Orchestrator writes a row per run with columns: `ts run_id status duration_sec n_steps budget_sec cost_usd aborted_reason goal`.
- `just experiments` renders the table; sort by `cost_usd` descending to surface expensive runs (`--by-cost` flag, if landed).
- `ExecutionPlan.budget_sec` is a hard wall-clock cap. Exceeding → orchestrator aborts, writes `status=aborted` to the TSV. Raise in the plan JSON if a run legitimately needs more.
- Token/dollar budgets are advisory at v1 (logged, not enforced). Constitution VIII caps tokens per model tier — opus is reserved for `orchestrator`, `meta-prompter`, `architect`, `sql-specialist` migrations only.

**"Plan validation failed."** Run `soup plan-validate <path>` (or `just plan-validate <path>`). Common causes:

- Unknown `TaskStep.agent` — not in `library.yaml` roster. Add the agent first (see [`docs/PATTERNS.md § 1`](PATTERNS.md#1-add-a-new-agent)).
- Absolute path in `context_excerpts` / `spec_refs` — paths must be relative to the repo root.
- Referenced path doesn't exist on disk — resolve order of operations: commit source artifact before authoring the plan that references it.
- `max_turns > 10` — Constitution II.3; split the task.

**"Subagent can't see my env var."** `orchestrator/agent_factory.py::_filter_parent_env` builds the child env from an explicit whitelist, not `os.environ` spread. Check:

- Is the var in `_DEFAULT_ENV_KEYS` (baseline) or `_DEFAULT_ENV_PREFIXES` (`LC_`, `CLAUDE_`, `SOUP_`)? Most keys you author fit the `SOUP_` prefix.
- For credentials: is it in `_STEP_INJECTABLE_ENV_KEYS` (`GITHUB_TOKEN`, `ADO_PAT`, `POSTGRES_*`, `OPENAI_API_KEY`, etc.)? If yes, add `TaskStep.env: {KEY: parent}` to the step that needs it.
- Anything outside both lists is silently dropped so a typo can't smuggle parent-env values. Extend the whitelist in `agent_factory.py` if you need a new one.

**Rule injection not firing.** `rules/global/*.md` is injected on every subagent. `rules/<stack>/*.md` is routed by `pre_tool_use.py` based on file extension — `.py` → `rules/python/`, `.cs` → `rules/dotnet/`, etc. `rules/compliance/<flag>.md` needs the flag in `.soup/intake/active.yaml` AND in the `COMPLIANCE_FLAGS_WITH_RULES` set in `.claude/hooks/subagent_start.py`.

**Worktree corrupted.** `just worktree-rm <name>` then `just worktree <name>`. Never commit a partially-working state to main (Constitution IX.3).

**RAG query returns nothing.** Usually `OPENAI_API_KEY` missing (required for LightRAG embeddings) or `rag-ingest` hasn't been run. `just rag-health` checks both. See [`docs/USER_GUIDE_RAG.md § 7`](USER_GUIDE_RAG.md#7-troubleshooting) for the full triage tree.

---

## FAQs

**Q: Do I need to run `/specify` if I have an intake YAML?**
A: No. `/intake --file <path>` drives `spec-writer` directly in Mode B and writes the spec. `/specify` is for free-text goals without an intake, or for `--extends <parent-spec>` extensions.

**Q: How do I use a different model than the agent default?**
A: Override `TaskStep.model` in the plan JSON (haiku/sonnet/opus), or set `CLAUDE_MODEL_DEFAULT` env (forwarded by the `CLAUDE_` prefix rule in `_filter_parent_env`). Tier overrides need written rationale in the PR body per Constitution VIII.

**Q: What if a `verify_cmd` needs a binary not on the allowlist?**
A: Add it to `TaskStep.extra_verify_bins` (the allowlist in `orchestrator/orchestrator.py::_parse_verify_cmd` extends at step level). For repo-wide additions, edit `.claude/settings.json` (or switch to a different `just preset`).

**Q: Why is the RAG search returning nothing?**
A: Most likely `OPENAI_API_KEY` is missing (required for LightRAG embeddings) or the source hasn't been ingested. `just rag-health` checks Postgres reachability, env, and `lightrag-hku` importability. If Postgres is up and the key is set, confirm the source: `just rag "*" --list-sources` (the MCP `rag_list_sources` tool from inside Claude Code).

**Q: Can I use soup on Linux/macOS?**
A: Yes. Windows is the primary environment, but `set shell := ["bash", "-cu"]` in the justfile means every recipe runs under bash — identically on Git Bash (Windows), macOS, Linux. See `README.md` for `brew`/`apt` prerequisite commands. Docker Desktop (Windows/macOS) or `docker.io` (Linux) required for Postgres.

**Q: How do I add a new agent?**
A: See [`docs/PATTERNS.md § 1`](PATTERNS.md#1-add-a-new-agent). Five steps: create `.claude/agents/<name>.md` with YAML frontmatter (name, description, model, tools), register in `library.yaml` (`type: agent`), whitelist the agent name in `schemas/execution_plan.py::TaskStep.agent` Literal, add a smoke test under `tests/agents/`, run `just test`.

**Q: How do I add a new rule?**
A: Drop a markdown file under `rules/<stack>/<name>.md`. `pre_tool_use.py` picks up all files in `rules/<stack>/` at session start — no registration needed; routing is glob-based. Global rules go under `rules/global/`. Compliance rules need one extra step (extend `schemas/intake_form.py::ComplianceFlag` and add to `COMPLIANCE_FLAGS_WITH_RULES`) — see [`docs/PATTERNS.md § 10`](PATTERNS.md#10-add-a-new-compliance-rule).

**Q: What's the cost of a typical run?**
A: A rough envelope from `logging/experiments.tsv`:

- `/quick` one-file fix: $0.05-$0.20.
- Simple greenfield (single endpoint + test + migration): $0.20-$0.80.
- Full greenfield (multi-integration intake, 10+ steps, RAG pre-pass): $1-$5.
- Large RAG ingest (1M token repo → graph build on sonnet): $5-$10 one-time (switch `SOUP_RAG_LLM_PROVIDER=openai` to cut this).

Check `just experiments --by-cost` to surface expensive runs; treat `BLOCK` + `cost_usd > 2` as a review-loop priority.

**Q: Is soup stable for customer-facing apps?**
A: Not yet. Current scope per the final audit panel is **internal apps with low blast radius** — tools, dashboards, automation, calibration surfaces, on-VPN services. Customer-facing critical-path systems (billing, health records, public APIs with SLAs) need additional review infrastructure and a harder QA gate than the v1 Stop-hook pipeline provides.

**Q: Where do I report bugs?**
A: Until the GitHub repo is public, file in `docs/issues/<YYYY-MM-DD>-<slug>.md` using the issue template. Include: the command run, the `.soup/runs/<run_id>/` dir, the tail of `logging/agent-runs/session-<session_id>.jsonl`, and `just doctor` output. Once published, use GitHub issues.

**Q: My plan validation keeps failing on `files_allowed`. What's the syntax?**
A: gitignore-style globs via `pathspec`, relative to the repo root. `src/app/main.py` (exact), `tests/**` (anything under tests/), `rules/*.md` (no recursion), `!tests/fixtures/**` (negation). See [`docs/PATTERNS.md § 0c`](PATTERNS.md#0c-files_allowed-glob-dialect).

**Q: A TDD RED-phase `verify_cmd` keeps being treated as GREEN.**
A: Prefix with `! ` (bash negation). A failing test exits non-zero → `! ` inverts to 0 → orchestrator treats as "verified" (good). A passing test (which should never happen yet) exits 0 → `! ` inverts to 1 → orchestrator treats as legitimate failure ("your RED test accidentally passed"). Never use `pytest ... || true` — that swallows every signal including crashes. See [`docs/PATTERNS.md § 0b`](PATTERNS.md#0b-tdd-red-phase-verify_cmd--canonical-pattern).

---

Further reading:

- [`CONSTITUTION.md`](../CONSTITUTION.md) — hard project rules (Articles I-X). Start here if you are shipping your first PR.
- [`CLAUDE.md`](../CLAUDE.md) — session steering; iron laws; "what NOT to do."
- [`docs/DESIGN.md`](DESIGN.md) — design tenets, pillars, flow diagrams, intake-form flow (§18), brownfield ingestion (§17).
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — hook choreography, memory model, cost accounting, Claude Code CLI invocation contract (§8).
- [`docs/ONBOARDING.md`](ONBOARDING.md) — 30-minute walkthrough for new engineers.
- [`docs/PATTERNS.md`](PATTERNS.md) — rubrics (skill vs. command vs. hook vs. rule), cookbooks (add-agent, add-skill, add-rule, add-template, add-compliance-flag), permission presets.
- [`docs/USER_GUIDE_RAG.md`](USER_GUIDE_RAG.md) — full RAG walkthrough (ingestion, querying, MCP, troubleshooting).
- [`intake/README.md`](../intake/README.md) — intake form field reference.
- [`.claude/agents/REGISTRY.md`](../.claude/agents/REGISTRY.md) — full agent roster, skill cross-refs, rule routing, dispatch context template.
- [`library.yaml`](../library.yaml) — catalog of skills and agents (The Library pattern).
