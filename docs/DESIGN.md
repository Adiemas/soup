# Soup — Design Synthesis

_Canonical agentic Claude Code framework for Streck internal app development._
_Synthesized from 17 reference repos (see `research/01-08-*.md`) on 2026-04-14._

## 1. Design tenets

1. **Spec > code.** Non-trivial work flows through `/constitution → /specify → /clarify → /plan → /tasks → /implement → /verify`.
2. **Fresh context per task.** Every substantive unit of work runs in a clean subagent with only the spec + its file scope. No conversation rot.
3. **Procedural gates, not suggestions.** TDD, verification, root-cause debugging are iron laws enforced by skills + hooks, not advisories.
4. **Deterministic where possible, agentic where necessary.** Meta-prompter decomposes agentically; orchestrator executes deterministically against a Pydantic-validated DAG.
5. **Hooks are the nervous system.** Observability, rule injection, QA gating, env loading — all live in hooks, not prompts.
6. **Atomic commits per task.** Enables bisect recovery; no phase-wide rollbacks.
7. **Stack-aware, not generic.** Rules/agents are routed by file extension + project metadata. No one-size-fits-all.
8. **File-based state.** `.soup/` holds plans, runs, memory as inspectable markdown/JSON. No runtime DB for orchestration state.
9. **Reference, don't clone.** Shared skills/agents live in a `library.yaml` catalog, pulled on demand (The Library pattern).
10. **Cite everything.** RAG retrievals return source spans; agents must attribute claims.

## 2. Architecture pillars

| # | Pillar | Source(s) | Implementation |
|---|---|---|---|
| 1 | **Skills** (procedural gates) | superpowers (5/5) | `.claude/skills/*/SKILL.md` — YAML frontmatter + iron-law markdown |
| 2 | **Agent roster** (stack-aware) | Adiemas, OpenHarness | `.claude/agents/*.md` — 20 specialists with model + tool budget |
| 3 | **Commands** (spec-driven) | spec-kit, cc-sdd, gsd | `.claude/commands/*.md` — `/constitution`, `/specify`, `/plan`, `/tasks`, `/implement`, `/verify`, `/quick`, `/rag-*` |
| 4 | **Hooks** (observability + gates) | Adiemas, install-and-maintain | `.claude/hooks/*.py` — SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, SubagentStart, Stop |
| 5 | **Rules** (routed by ext) | Adiemas | `rules/{global,python,dotnet,react,typescript,postgres}/*.md` |
| 6 | **Schemas** (Pydantic validation) | Adiemas | `schemas/*.py` — `ExecutionPlan`, `Task`, `QAReport`, `Spec`, `AgentLog` |
| 7 | **Orchestrator** (DAG executor) | Archon, Adiemas, gsd | `orchestrator/` — waves, worktree-isolated, fresh subagent per step |
| 8 | **Meta-prompter** (task → plan) | Adiemas, autoresearch | `orchestrator/meta_prompter.py` — opus-level decomposition, cost-aware model choice |
| 9 | **RAG** (org docs) | LightRAG (5/5), Archon | `rag/` — LightRAG + Postgres + MCP wrapper; sources: GitHub, ADO wiki, filesystem, web |
| 10 | **CLI wrappers** (tool surface) | CLI-Anything | `cli_wrappers/` — `--json` wrappers for `az devops`, `psql`, `docker`, `dotnet`, `git` |
| 11 | **Templates** (stack starters) | Adiemas | `templates/{python-fastapi-postgres,dotnet-webapi-postgres,react-ts-vite,fullstack}/` |
| 12 | **Justfile** (three-mode CLI) | disler, gsd | Deterministic / supervised / interactive recipes |
| 13 | **Logging** (JSONL + TSV) | Adiemas, autoresearch | `logging/agent-runs/*.jsonl` + `logging/experiments.tsv` |
| 14 | **Library catalog** (distribution) | The Library | `library.yaml` — pull skills/agents from canonical repos on demand |
| 15 | **Worktrees** (task isolation) | Archon, superpowers | `.soup/worktrees/` — per-feature git isolation |
| 16 | **Memory** (session + long-term) | OpenHarness, nanobot | `CLAUDE.md` (session) + `MEMORY.md` (long-term) + `.soup/memory/` (dream-consolidated) |

## 3. Core data contracts

**`schemas/execution_plan.py`** — meta-prompter → orchestrator contract:
```python
class TaskStep(BaseModel):
    id: str                                # "S1", "S2", ...
    agent: Literal[<agent_roster>]
    prompt: str                            # full subagent brief
    depends_on: list[str] = []             # other step IDs
    parallel: bool = False                 # can run in wave
    model: Literal["haiku", "sonnet", "opus"] = "sonnet"
    verify_cmd: str                        # bash command whose exit 0 = pass
    files_allowed: list[str] = []          # glob constraints
    max_turns: int = 10
    rag_queries: list[str] = []            # run before spawn
    context_excerpts: list[str] = []       # "path#anchor" or "path:from-to"
    spec_refs: list[str] = []              # spec paths; loaded whole

class ExecutionPlan(BaseModel):
    goal: str
    constitution_ref: str                  # path to CONSTITUTION.md snapshot
    steps: list[TaskStep]
    budget_sec: int = 3600
    worktree: bool = True
    regression_baseline_cmd: str | None = None       # brownfield freeze
    regression_baseline_timeout_sec: int = 120
    compliance_flags: list[str] = []                 # mirrored from intake
```

`context_excerpts` and `spec_refs` (added cycle-2) let a TaskStep carry
project-specific domain knowledge into the subagent's fresh context
without bloating the shared roster prompt. The field validator rejects
absolute paths; `ExecutionPlanValidator` then enforces that every
referenced path exists on disk. Resolution happens in
`orchestrator/agent_factory.py::_compose_brief` — see §17 for the
brownfield-ingestion flow that populates them, and `ARCHITECTURE.md §8`
for injection timing.

`regression_baseline_cmd` (added iter-2) activates the
`brownfield-baseline-capture` skill at the orchestrator level: the
command runs once pre-S1 and once post-final-wave; their diff drives
the regression status. Subject to the same argv[0] allowlist as
`TaskStep.verify_cmd` — the parser in
`orchestrator/orchestrator.py::_parse_verify_cmd` is the single point
of enforcement. Artefacts land under `.soup/baseline/<run_id>/`;
non-zero diff marks `RunState.status == "regression"` (a distinct
status from `passed`/`failed`/`aborted`). `compliance_flags` is a
simple string-tag list mirrored from the intake form; the
`pre_tool_use` hook is the registrar of which tags map to which rule
injections (default: empty / no-op).

**`schemas/qa_report.py`** — Stop-hook QA gate:
```python
class Finding(BaseModel):
    severity: Literal["critical", "high", "medium", "low"]
    category: Literal["security", "correctness", "style", "test", "coverage"]
    file: str; line: int | None; message: str

class QAReport(BaseModel):
    verdict: Literal["APPROVE", "NEEDS_ATTENTION", "BLOCK"]
    findings: list[Finding]
    test_results: dict  # {passed:int, failed:int, skipped:int, coverage:float}

# Blocking rules (Adiemas pattern):
# - any critical security finding → BLOCK
# - any failing test → BLOCK
# - 3+ critical correctness findings → BLOCK
# - coverage <70% → NEEDS_ATTENTION
```

## 4. Flow — canonical `/implement` run

```
User: /implement <task>
  ↓
meta-prompter (opus) ──→ ExecutionPlan JSON
  ↓ (Pydantic-validated)
orchestrator.run(plan)
  ↓
for each wave of ready steps:
  ├─ spawn fresh subagent per step (parallel where allowed)
  │   ├─ SessionStart hook   → load .env, prime codebase
  │   ├─ subagent_start hook → inject rules (by ext) + RAG context
  │   ├─ agent executes (sonnet/haiku/opus per step)
  │   ├─ post_tool_use hook  → JSONL log every tool call
  │   └─ agent exits with verify_cmd output
  ├─ orchestrator runs verify_cmd → pass/fail
  ├─ on pass: atomic git commit in worktree
  └─ on fail: auto-debug subagent (systematic-debugging skill)
  ↓
Stop hook → qa-orchestrator dispatches code-reviewer + security-scanner + verifier in parallel
  ↓
QAReport synthesized
  ├─ APPROVE      → merge worktree into branch, create PR
  ├─ NEEDS_ATTENTION → human review required
  └─ BLOCK        → revert, dispatch `verifier` (fix-cycle role)
```

## 5. Skill catalog (adapted from superpowers, extended)

**Process (rigid):**
- `brainstorming` — Socratic exploration before any creative work
- `writing-plans` — approved design → bite-sized tasks
- `executing-plans` — checkpointed batch execution
- `tdd` — RED/GREEN/REFACTOR enforcement; auto-deletes pre-test code
- `systematic-debugging` — 4-phase root cause; hard-block on guessing
- `verification-before-completion` — evidence before claims always

**Coordination (flexible):**
- `subagent-driven-development` — fresh-context per-task
- `dispatching-parallel-agents` — concurrent independent work
- `using-git-worktrees` — per-feature isolation
- `requesting-code-review` — spec-compliance first, code-quality second
- `finishing-a-development-branch` — merge/PR/discard decision

**Soup-specific (new):**
- `agentic-rag-research` — autonomous deep-research loop over org knowledge (autoresearch-style)
- `spec-driven-development` — the canonical `/constitution → /implement` flow
- `meta-prompting` — producing ExecutionPlan JSON from natural-language goals
- `cli-wrapper-authoring` — CLI-Anything 7-phase for new tools
- `contract-drift-detection` — detect→compare→regenerate→verify gate for cross-stack contracts (OpenAPI ↔ TS types, SQL schema ↔ ORM model, `.proto` ↔ clients). Iron law: "A contract change without a client regen is a silent bug."
- `brownfield-baseline-capture` — enumerate→capture→modify→diff freeze/regression loop for any plan touching an existing passing surface. Iron law: "Freeze what's already working before you change it. Diff before you ship." Pairs with the new `ExecutionPlan.regression_baseline_cmd` field; orchestrator runs the command pre-S1 and post-final, diffs the artefacts, surfaces regression to the QA gate as a high-severity finding.

## 6. Agent roster (v1)

| Agent | Model | Role | Tool budget |
|---|---|---|---|
| `orchestrator` | opus | Top-level dispatcher; runs ExecutionPlan | All |
| `meta-prompter` | opus | Goal → ExecutionPlan JSON | Read/Grep/Glob/WebFetch |
| `architect` | opus | High-level design | Read/Grep/WebFetch |
| `spec-writer` | sonnet | `/specify` author | Read/Write |
| `plan-writer` | sonnet | `/plan` author | Read/Write |
| `implementer` | sonnet | Single-task code writer | Read/Edit/Write/Bash |
| `python-dev` | sonnet | Python specialist | Read/Edit/Write/Bash |
| `dotnet-dev` | sonnet | C#/.NET specialist | Read/Edit/Write/Bash |
| `react-dev` | sonnet | React specialist | Read/Edit/Write/Bash |
| `ts-dev` | sonnet | TypeScript specialist | Read/Edit/Write/Bash |
| `sql-specialist` | opus | Postgres schemas, migrations | Read/Edit/Write/Bash |
| `full-stack-integrator` | sonnet | Cross-stack contracts (OpenAPI ↔ TS types, SQL ↔ ORM, Protobuf); regenerates both sides in one step | Read/Grep/Glob/Edit/Write/Bash |
| `test-engineer` | sonnet | Test author (TDD red phase) | Read/Edit/Write/Bash |
| `code-reviewer` | sonnet | Static review vs. spec + rules | Read/Grep |
| `security-scanner` | sonnet | OWASP + secrets + supply chain; respects repo `.gitleaks.toml` | Read/Grep/Bash |
| `red-team-critic` | sonnet | Adversarial review on round ≥ 2 of `/review`; emits `CritiqueReport` | Read/Grep/Glob |
| `over-eng-critic` | sonnet | Radical-simplification review on round ≥ 2 of `/review`; emits `CritiqueReport` | Read/Grep/Glob |
| `qa-orchestrator` | sonnet | Dispatches reviewer/scanner/verifier | Agent |
| `verifier` | sonnet | Runs `verify_cmd`, diagnoses failures | Read/Bash |
| `rag-researcher` | sonnet | Autonomous research loop over org docs | Read/Bash/Agent |
| `docs-ingester` | haiku | Add source to RAG | Bash |
| `github-agent` | sonnet | GitHub PR/issue/CI via `gh` | Bash |
| `ado-agent` | sonnet | ADO work items/repos/pipelines via `az devops` | Bash |

## 7. Command surface (v1)

| Command | Purpose | Backs onto |
|---|---|---|
| `/constitution` | Set project principles | `CONSTITUTION.md` |
| `/specify <goal>` | Write user-facing spec | `spec-writer` |
| `/clarify` | Resolve ambiguities | Interactive HITL |
| `/plan` | Architecture + tech | `plan-writer` + `architect` |
| `/tasks` | Break plan into TDD-shaped tasks | `plan-writer` |
| `/implement [task]` | Execute (orchestrator + waves) | `orchestrator` |
| `/verify` | QA gate + UAT | `qa-orchestrator` |
| `/quick <ask>` | Ad-hoc no-planning path | `implementer` |
| `/map-codebase` | Pre-planning survey | `Explore`-style subagent |
| `/review` | Cross-agent peer review | `code-reviewer` |
| `/install` | Bootstrap project (three-mode) | Setup hooks |
| `/rag-search <q>` | Query org knowledge | `rag-researcher` |
| `/rag-ingest <src>` | Add source (GitHub/ADO/fs/web) | `docs-ingester` |
| `/soup-init <template>` | New internal app from template | Templates |

## 8. Hook choreography

```
SessionStart          → hooks/session_start.py      (load .env, prime summary)
UserPromptSubmit      → hooks/user_prompt_submit.py (detect intent, suggest skill)
PreToolUse (Edit|Write) → hooks/pre_tool_use.py     (inject rules by file ext)
PostToolUse (*)       → hooks/post_tool_use.py      (JSONL log, validate output)
SubagentStart         → hooks/subagent_start.py     (inject RAG context + rules)
Stop                  → hooks/stop.py               (dispatch qa-orchestrator)
```

All hooks write to `logging/agent-runs/session-{sessionId}.jsonl` — one structured event per tool call. Stop hook writes `logging/experiments.tsv` (autoresearch-style append-only metrics table).

## 9. Justfile — three-mode CLI (disler pattern)

```
just init                       # bootstrap dev env
just plan "<goal>"              # deterministic: meta-prompter only (dry-run)
just go "<goal>"                # supervised: plan + execute + auto-verify
just go-i "<goal>"              # interactive: plan + HITL at each wave
just rag "<query>"              # query org knowledge
just rag-ingest <source>        # add doc source
just verify                     # QA gate on current branch
just worktree <name>            # create isolated worktree
just templates                  # list stack templates
just new <template> <name>      # scaffold new internal app
just test-self                  # run framework self-tests
```

## 10. Deferred / explicitly NOT copied

- Archon's multi-platform adapters (Slack/Telegram/Discord) — overkill for internal dev
- Nanobot's Dream-consolidation — nice, defer until memory volume demands it
- TDAD full AST graph — future upgrade; v1 uses simpler file-based impact
- CLI-Anything auto-generation — v1 writes wrappers manually; automate later
- `agent-factory` / `agent-forge` / `agentic-dev-framework` / `claude-code-training` (Adiemas) — all 404'd; skip
- Bowser's full Playwright layer — only relevant when we add browser-based UAT subagents

## 11. Build phase plan (parallel subagents)

Seven parallel build agents, one per sub-pillar:
1. **A** — `.claude/settings.json` + hooks (session/pre/post/subagent/stop) + `rules/` tree
2. **B** — `.claude/agents/*.md` roster (20 agents) + `.claude/skills/` (12 skills)
3. **C** — `.claude/commands/*.md` (full command surface)
4. **D** — `schemas/*.py` + `orchestrator/` (DAG executor, meta-prompter, agent factory)
5. **E** — `rag/` pipeline (LightRAG wrapper, sources, MCP server)
6. **F** — `cli_wrappers/` (ADO/psql/docker/dotnet/git) + `templates/` (4 stacks)
7. **G** — `justfile` + `CLAUDE.md` + `CONSTITUTION.md` + `library.yaml` + `pyproject.toml` + `README.md` + `docker/`

Review loop: build → mock-app subagent exercises framework → 3-reviewer panel critiques → patch → repeat (cap 5 cycles Python path, 3 cycles C# path).

## 17. Brownfield ingestion

Many repos Soup targets already run a document-driven multi-agent
pipeline — `AGENT_*_SPEC.md`, `MASTER_PLAN.md`, `*_HANDOFF.md` — that
predates any Soup machinery. Rewriting these by hand into
`ExecutionPlan` JSON is the single biggest onboarding tax for
existing repos (documented in
`docs/real-world-dogfood/warhammer-40k-calculator.md`). §17 is the
ingestion lever that closes that gap.

### Flow

```
prose doc (AGENT_*_SPEC.md, *_PLAN.md, *_HANDOFF.md)
    │
    ▼  just ingest-plans "<glob>"
    │  (= soup ingest-plans <glob>)
    │
[meta-prompter INGEST mode]
    │ extracts work items (does NOT invent them)
    │ emits defaults for fields prose cannot fill + `TODO:` markers
    ▼
.soup/ingested/<source-slug>.plan.json
    │
    ▼  MANUAL REVIEW GATE (non-optional)
    │  - resolve every `TODO: define verify_cmd`
    │  - resolve every `TODO: scope files_allowed`
    │  - resolve every `TODO: pick specialist agent`
    │  - resolve every `TODO: clarify`
    │
    ▼  soup plan-validate <path>
    │
    ▼  move into .soup/plans/<slug>.json
    │
    ▼  /implement
```

### Why INGEST mode is a separate prompt, not a flag on `plan_for`

The planning prompt (`plan_for(goal)`) is explicitly creative — it
decomposes a natural-language goal into a new DAG. The ingest prompt
is explicitly *anti-creative* — it extracts what prose already says
and marks its own gaps. Sharing the prompt would dilute both
behaviours; keeping them separate keeps the iron law clear.

See `orchestrator/meta_prompter.py::ingest_prose` for the
implementation and `.claude/commands/ingest-plans.md` for the
operator-facing contract. The output directory (`.soup/ingested/`,
not `.soup/plans/`) is a deliberate quarantine — `soup go` and
`/implement` never pick up unreviewed skeletons.

### When NOT to use

- **Greenfield work.** Use `/specify + /plan + /tasks` — those are
  designed to synthesize a new DAG, not salvage one.
- **Single-file prose.** For one short doc, reading it and hand-
  authoring a plan is faster than running ingest, reviewing, then
  validating.
- **Status dumps.** `*_STATUS.md` / `CURRENT_STATUS_HANDOFF.md`
  describe past work, not future work — ingesting them produces a
  plan that retells what already happened. Use `/map-codebase` for a
  situational-awareness pass instead.

## 18. Intake-form flow

For brand-new Streck apps, the entry point is `/intake`, not
`/specify`. `/intake` consumes a validated YAML form
(`schemas/intake_form.py::IntakeForm`) and threads a structured record
through the whole pipeline — no contract ever lives in prose alone.

### Flow

```
intake/<app_slug>.yaml           (human edits; source of truth for form content)
        │
        ▼  /intake --file <path>
        │
        │  IntakeForm.model_validate(path)
        │  (+ optional researcher pre-pass when --brownfield set;
        │   writes .soup/research/<slug>-findings.md)
        │
        ▼  spec-writer Mode B
        │  field-to-section map; per-integration anchors
        │
        ▼  specs/<slug>-<date>.md                  (frozen narrative)
        │  specs/<slug>-<date>.intake.yaml         (frozen YAML audit trail)
        │  .soup/intake/active.yaml                (hook-readable pointer)
        │
        ▼  /plan
        │  reads specs/<slug>-<date>.intake.yaml if present;
        │  passes stack_preference / deployment_target /
        │  compliance_flags / integrations[] into architect prompt
        │  as STRUCTURED inputs (not re-derived from prose).
        │
        ▼  .soup/plans/<slug>.md
        │
        ▼  /tasks
        │  emits per-integration context_excerpts using the
        │  `#integration-<kind>-<ref-slug>` anchors in the spec.
        │
        ▼  /implement
        │  orchestrator spawns subagents; subagent_start.py reads
        │  .soup/intake/active.yaml, extracts compliance_flags[],
        │  and appends rules/compliance/<flag>.md to every
        │  subagent's additionalContext (on top of the always-
        │  injected rules/global/*.md).
```

### Why the flow has three resting artifacts (not one)

The intake YAML lives in three places by design, each with a distinct
lifecycle:

1. **`intake/<app_slug>.yaml`** — the editable human source.
   Reviewed in PRs. Survives beyond the first spec.
2. **`specs/<app_slug>-<date>.intake.yaml`** — the frozen audit
   trail. Travels with the dated spec per Constitution I.4. Never
   mutated after `/intake` writes it.
3. **`.soup/intake/active.yaml`** — a symlink-free pointer to the
   most recent intake. Hook-readable without a slug parameter.
   Replaced on every `/intake` run; treated as a pointer, not a
   history.

Keeping `.soup/intake/active.yaml` out of `specs/` is deliberate:
`specs/` holds spec-frozen artefacts (Article I.4), and `active.yaml`
is not frozen — it rolls forward to whichever intake ran most
recently. Hooks that need slug-free access use `active.yaml`;
auditors reading the history of a particular spec use the dated
`.intake.yaml` under `specs/`.

### What the intake form unlocks downstream

- **Per-integration context scoping.** The `## Integrations` section
  in a Mode B spec carries one `### <kind>: <ref>` subsection per
  integration with a deterministic anchor
  (`#integration-rest-api-assettracker-streck-internal`, ...).
  `tasks-writer` emits `context_excerpts` per integration, so an
  adapter implementation step sees only its integration — not the
  full table.
- **Flag-driven rule injection.** `compliance_flags[]` is the lever
  that converts intake metadata into runtime behaviour.
  `subagent_start.py` loads `rules/compliance/<flag>.md` for each
  flag on top of `rules/global/*.md`. See `rules/compliance/README.md`
  for the flag-to-rule mapping. `public` and `internal-only` are
  labelling flags only (no rule file).
- **Clean spec body.** `stack_preference`, `deployment_target`, and
  `requesting_team` never land in the spec — they live in the
  stashed YAML and flow into `/plan`'s architect prompt as structured
  inputs. Constitution Article I (what-not-how) is preserved.
- **Brownfield extension path.** `/intake --brownfield <repo-path>`
  dispatches the `researcher` utility agent BEFORE `spec-writer` so
  the spec cites concrete file+line coordinates from the existing
  repo. The findings file (`.soup/research/<slug>-findings.md`) is
  referenced from the spec's `## Brownfield notes` section and
  consumed downstream by `tasks-writer` for `context_excerpts`
  hydration. `/specify --extends <parent-spec>` is the complementary
  under-soup path (extending a parent spec that already lives in
  `specs/`).

### What stays out of the intake form

- Code. Ever.
- Tech selection rationale (goes on the architect's design doc).
- Estimated hours / sprint mapping (goes on the plan's Budget).
- Agent roster choices (the orchestrator picks).

The form is a shape-validator for **intent**, not an early plan.
