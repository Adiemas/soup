# Iteration 3 dogfood — multi-intake batch mode / sprint planning

**Date:** 2026-04-14
**Mode:** Simulated portfolio planning (paper trace; no real batch run).
**Subject:** what happens when the Streck PM hands soup **five** intake
forms for the same quarter and expects a coherent sprint plan. Sibling
to `iter2-intake-form.md` (which validated the single-app flow) and
`iter2-brownfield-integration.md` (which validated single-repo
extension).

## Scenario: 5 intakes

The Lab Ops PM drops the following YAMLs on the engineering lead's
desk on 2026-04-14 and asks for a Q2+Q3 plan by Friday:

| # | app_slug | Source | Headline integrations | Deadline | Compliance |
|---|---|---|---|---|---|
| 1 | `pipette-calibration-dashboard` | `intake/examples/pipette-calibration-dashboard.yaml` | AssetTracker REST, ADO `streck/LabOps`, `lab-ops-db` Postgres, `streck/lab-design-system`, mail relay | 2026-06-14 | `lab-data`, `internal-only` |
| 2 | `asset-inventory-lite` | `intake/examples/asset-inventory-lite.yaml` | `lab-ops-db` Postgres, `streck/lab-design-system` | 2026-05-15 | `internal-only` |
| 3 | `reagent-expiration-monitor` | new | `lab-ops-db` Postgres (**POST to `asset_tracker` schema**), AssetTracker REST (read), mail relay | 2026-07-01 | `lab-data`, `internal-only` |
| 4 | `lab-ticket-triage` | new | ADO `streck/LabOps` (work items read/write), mail relay, internal SMTP | 2026-06-30 | `internal-only` |
| 5 | `sample-intake-receiver` | new | SFTP (inbound samples), `sample-intake-db` Postgres, notification REST API | 2026-08-01 | `phi`, `lab-data` |

Cross-intake topology (derivable from the YAMLs alone):

- **Shared Postgres host** — #1, #2, #3 all reference
  `postgres://lab-ops-db.streck.internal/lab_ops`. #5 is a
  different cluster (`sample-intake-db`).
- **Shared React component library** — #1, #2 both pull
  `streck/lab-design-system`. #3 and #4 are API-only (no React
  surface in the stated YAMLs).
- **Shared mail relay** — #1, #3, #4 all call
  `https://mailrelay.streck.internal/api/v1`.
- **Shared ADO project** — #1 reads `streck/LabOps`; #4 reads **and
  writes** `streck/LabOps`. #4 is the stricter auth surface; #1
  can piggyback on the read path #4 must already harden.
- **Hard dependency** — #3 `reagent-expiration-monitor` writes into
  the `asset_tracker` schema that #2 `asset-inventory-lite` is
  standing up. #3 must not start until #2's migrations land.
- **Soft dependency** — #1 benefits from #2's audit-log table (same
  schema), but #1 can stub a read-only copy if #2 slips.

None of this is visible to soup today. Each intake produces an
independent spec, plan, and ExecutionPlan with no knowledge of the
other four.

## Current gap (soup is single-intake)

The entire pipeline — `schemas/intake_form.py`,
`.claude/commands/intake.md`, `.claude/commands/plan.md`,
`.soup/intake/active.yaml`, `orchestrator/cli.py` — assumes one intake
→ one spec → one plan → one execution. Evidence:

- **`IntakeForm.from_yaml(path)`** takes a single path. No
  `from_yaml_dir(...)` or `.portfolio` aggregation
  (`schemas/intake_form.py:225`).
- **`/intake`** parses one `--file <path>` and writes a single
  `active.yaml` pointer (`.claude/commands/intake.md` §9). A second
  `/intake` invocation **replaces** `active.yaml` — there is no
  concept of "five active intakes for this sprint."
- **`/plan`** resolves the stashed intake YAML for the slug it was
  invoked on (`.claude/commands/plan.md` step 2). It has no
  cross-spec awareness.
- **`architect`** is briefed with one spec, one intake block, and one
  constitution (`.claude/agents/architect.md`). It cannot see other
  intakes. It has no authority to propose shared infrastructure
  because it has no evidence any other app exists.
- **`orchestrator/cli.py`** exposes `plan`, `plan-validate`, `run`,
  `go`, `go-i`, `quick`, `ingest-plans` — all single-plan. The
  closest multi-plan surface is `ingest-plans <glob>` which emits
  **independent skeletons** with no cross-plan graph
  (`orchestrator/cli.py:157-199`).
- **`ExecutionPlan.budget_sec`** exists per plan
  (`schemas/execution_plan.py:246`) but there is no portfolio-level
  aggregator. `cost_usd` lands in run logs
  (`orchestrator/orchestrator.py`, `orchestrator/providers.py`) per
  run — no sprint roll-up.
- **DESIGN.md §18** diagrams the intake flow as linear-one-shot;
  §17 (brownfield ingestion) supports multi-file *glob* input but
  each ingested doc becomes an **independent** plan skeleton (the
  §17 flow is explicitly quarantined at `.soup/ingested/` and
  calls for "manual review gate" per file).

Net: a PM handing soup five intakes gets five parallel runs of the
single-intake pipeline, each forgetting the other four exist. Shared
Postgres drift, duplicate adapters, overlapping audit-log tables, and
ordering violations (app #3 before app #2) are the guaranteed failure
modes.

## Proposed additions

### P1. `/intake --batch <dir-of-yamls>` command

Shape: a new operator-facing command that accepts a directory of
YAMLs, validates each against `IntakeForm`, and emits a **Portfolio**
artefact rather than a single spec.

```
/intake --batch intake/q3-2026/
  # validates intake/q3-2026/*.yaml against IntakeForm
  # refuses to proceed if any form is malformed (all-or-nothing)
  # writes portfolio/q3-2026-<date>.md  (human narrative)
  # writes portfolio/q3-2026-<date>.portfolio.yaml  (frozen audit)
  # writes .soup/portfolio/active.yaml  (hook pointer)
  # prints: {n_intakes, dependency_graph_summary, shared_infra_summary,
  #          total_budget_sec_estimate, compliance_flag_union}
```

Operator ergonomics: `/intake --batch` should accept `--file ...`
repeated too (`/intake --file a.yaml --file b.yaml --file c.yaml`) so
a small sprint can be assembled without a directory. The directory
form is the default path; the list form is an escape hatch.

Iron law: `/intake` without `--batch` continues to work exactly as
today. Batch mode is **additive**, not a replacement — the single-app
path is the 80% case and must not regress.

### P2. `portfolio-architect` agent (opus)

New agent card at `.claude/agents/portfolio-architect.md`. Dispatched
by `/intake --batch` after all YAMLs validate. Differs from
`architect.md` in scope:

| | `architect` (today) | `portfolio-architect` (new) |
|---|---|---|
| Input | 1 spec + 1 intake block | N intakes + 0 specs (specs not written yet) |
| Output | 1 design doc per spec | 1 portfolio design doc: shared-infra proposal + per-app ordering + cross-app risk register |
| Model | opus | opus (reasoning across 5+ intakes needs the wide context window; this is where Opus earns its keep) |
| Invokes | `plan-writer` for one plan | `plan-writer` per intake **after** the shared-infra proposal is accepted |
| Auth | read-only | read-only |

Deliverable shape (markdown):
1. **Portfolio context** — which PM, which sprint, which deadlines.
2. **Dependency graph** — DAG over the N intakes (hard vs soft
   edges). Rendered as both a mermaid diagram and a topological
   order table.
3. **Shared-infrastructure proposal** — per shared resource
   (`lab-ops-db` Postgres, `streck/lab-design-system`, mail relay,
   `streck/LabOps` ADO): the shared library / shared config /
   shared auth pattern, the app(s) that own it, the app(s) that
   consume it.
4. **Ordering / scheduling** — which intakes can run in parallel,
   which must serialize, which have hard blockers on shared
   infrastructure being lifted out first.
5. **Aggregated risks** — compliance-flag union, cross-app data
   flow (e.g. "app #3's writes land in app #2's schema"), timeline
   feasibility given the compounded budget.
6. **Explicit non-goals** — what the portfolio deliberately does
   NOT unify (e.g. "app #5's `sample-intake-db` stays a separate
   cluster; no cross-cluster joins").

Iron laws (carried from `architect.md`):
- Read-only. Never edits.
- Must name files/modules (extended to: must name **which repo** a
  shared component lives in — `streck/lab-shared-py` etc.).
- 3-failure escalation path unchanged.

### P3. `schemas/portfolio.py` — Portfolio model

Canonical Pydantic model to match `intake_form.IntakeForm`'s role at
the single-app level:

```
Portfolio
├── portfolio_slug: str           # kebab-case, e.g. "q3-2026"
├── portfolio_name: str
├── sprint_window: tuple[date, date] | None
├── intakes: list[IntakeForm]     # validated at load time
├── dependency_graph: list[Dep]   # Dep(from=slug, to=slug, kind=hard|soft, reason=str)
├── shared_infra: list[SharedComponent]
│     ├── name: str               # "lab-ops-db", "lab-design-system"
│     ├── kind: IntegrationKind   # reuses IntegrationKind literal
│     ├── ref: str                # the locator string, deduped
│     ├── consumed_by: list[str]  # intake slugs that use it
│     ├── owner_slug: str | None  # which intake owns the shared lib (if any)
│     └── pattern: Literal["shared-client-lib", "shared-schema",
│                           "shared-secrets", "shared-template", "none"]
├── compliance_union: list[ComplianceFlag]  # union over intakes (deduped)
└── estimated_total_budget_sec: int         # sum-of-plans post-shared-infra extraction
```

`Portfolio.from_yaml_dir(path)` is the canonical constructor, mirroring
`IntakeForm.from_yaml`. It enumerates `*.yaml` under `path`, validates
each through `IntakeForm.from_yaml`, then runs the dependency + shared-
infra detection pass (see P4/P5).

Validators worth coding:
- **Slug uniqueness.** Two intakes with the same `app_slug` abort the
  batch (soft forks belong in `/specify --extends`, not the batch
  entry point).
- **Deadline ordering vs dependency_graph.** If intake `B` depends on
  intake `A` and `B.deadline < A.deadline`, raise a model-level
  validator error (the PM needs to know the timeline is infeasible
  before the architect runs).
- **Compliance-flag union sanity.** Re-apply the single-intake
  `public` ⊥ {sensitive} rule at the union level — surfaces the case
  where one intake declared `public` and another in the same sprint
  declared `phi`, which means the sprint's shared infra cannot be
  hosted in a public-tier account.

### P4. `orchestrator/portfolio.py` — cross-plan scheduler

New module, sibling to `orchestrator/orchestrator.py` and
`orchestrator/meta_prompter.py`. Responsibilities:

1. Consume a validated `Portfolio` + per-intake `ExecutionPlan`
   artefacts.
2. Build a meta-DAG where **each node is an ExecutionPlan** (not a
   TaskStep) and edges come from `Portfolio.dependency_graph`.
3. Expose `run_portfolio()` — runs plans in topological order, with
   parallelism for plans that share no edge.
4. Integrate with existing `.soup/runs/` per-run logging but add a
   `.soup/portfolio-runs/<portfolio-slug>-<date>/` umbrella that
   aggregates the underlying run dirs.
5. Single command surface:
   `soup portfolio run <portfolio-slug>` — mirrors `soup run
   <plan>` but iterates the meta-DAG.

Why it's a separate module: the current
`orchestrator.Orchestrator` resolves `TaskStep.depends_on` within a
single `ExecutionPlan`. Extending it to resolve cross-plan deps
would leak portfolio concepts into a class whose concurrency model,
budget accounting, and state persistence are all scoped to one
plan. A sibling module keeps the per-plan orchestrator untouched
and wraps it.

### P5. Shared-infrastructure template layer

Today `templates/` holds six per-app templates
(`python-fastapi-postgres`, `dotnet-webapi-postgres`,
`react-ts-vite`, `fullstack-python-react`, `nextjs-app-router`,
`ts-node-script`). None of them scaffold a **shared-across-apps**
artefact.

Propose a new tier:

- `templates/shared-lib/python-postgres-reader/` — a Python package
  scaffold with pre-baked `asyncpg` pool, `pydantic-settings` config,
  and a `readonly_role` pattern. Invoked when `portfolio-architect`
  flags ≥2 intakes that do read-only Postgres against the same
  cluster.
- `templates/shared-lib/react-component-consumer/` — a tsconfig
  + vite-config snippet for apps that pull `streck/lab-design-system`.
  Reuses the dedup from today's `fullstack-python-react` template.
- `templates/shared-lib/ado-client/` — a TypeScript/Python ADO
  client wrapping PAT rotation and retry. Flagged when ≥2 intakes
  reference the same `ado-project`.
- `templates/shared-lib/mail-relay-client/` — wraps the `/messages`
  POST with circuit-breaker + retry. Flagged when ≥2 intakes touch
  `mailrelay.streck.internal`.

Detection logic lives on `portfolio-architect`'s shared-infra pass:
for each `SharedComponent`, map `(kind, ref) -> template_slug`. If a
match exists, propose the shared-lib scaffold as a **pre-app-zero
step** in the meta-DAG: it must land before any of its consumers.

Worth noting: this is also where iter-3's F7 (ADO work-item threading)
fits — a shared ADO client is the natural home for `ado-wi://` URI
resolution.

### P6. Sprint-cost aggregator (`soup portfolio budget`)

`ExecutionPlan.budget_sec` exists per plan; `cost_usd` lands in run
logs via `orchestrator/providers.py`. Neither rolls up.

Add two commands:

- `soup portfolio budget <portfolio-slug>` — reads the meta-DAG,
  sums `budget_sec` across all plans, converts to $USD using the
  model-price table already in `orchestrator/providers.py`
  (`cost_usd` per step). Output: a table with per-intake
  breakdown + total + top-3 cost-driver steps across the whole
  portfolio.
- `soup portfolio cost <portfolio-slug> --actual` — after a run,
  aggregates realised `cost_usd` from `.soup/runs/<plan>/**/cost.json`
  into a single roll-up. Used for sprint retrospectives.

Why it's not on the per-plan CLI: a sprint's $1.2k estimate is a
**different budget conversation** (PM + Engineering Lead) than a per-
app $240 estimate (tech lead on that app). Different consumers want
different levels of rollup.

### P7. Stakeholder report generator (`/portfolio-report`)

After `/intake --batch` and `portfolio-architect` run, the PM wants
one document they can forward to the Director:

- Timeline (from `dependency_graph` + `deadline`s, rendered Gantt-
  style).
- Risk summary (from `portfolio-architect.md` §Risks, aggregated).
- Resource needs (engineer-weeks estimate derived from
  `constraints` across intakes — the pipette-dashboard intake
  already says "3 weeks of one full-time engineer"; the
  asset-inventory says "1 week of one engineer"; the new three
  need equivalent phrasing).
- Shared-infra dependencies (from P5 proposals).
- Cost estimate (from P6).
- Compliance posture (union of `compliance_flags` across the
  portfolio; flagged obligations rolled up).

New command: `/portfolio-report` (dispatches a `sonnet` agent that
reads the portfolio doc + per-plan markdown and renders a single
`docs/portfolios/<portfolio-slug>-report.md`). Keep it `sonnet`, not
`opus` — this is a rendering job, not a design job.

### P8. Shared Postgres read-only access pattern

Concrete rule/pattern artefact at
`rules/patterns/shared-postgres-reader.md` that `portfolio-architect`
cites when ≥2 intakes do `read` against the same Postgres cluster:

- Canonical role: `app_<cluster>_reader` with `SELECT` on the
  specified schemas only.
- Connection-pool sizing: `pool_size = ceil(sum(app_rps) * p95_query_ms
  / 1000) + headroom`.
- Secret rotation: Vault integration — one secret, N apps, rotated
  together.
- Migrations ownership: exactly one intake owns the schema
  (typically the app that first declares it). Others read.

This is the pattern that resolves the
pipette-dashboard ↔ asset-inventory ↔ reagent-expiration
three-app overlap in the example.

### P9. Shared secrets / vault pattern

Companion to P8. `rules/patterns/shared-secrets-vault.md`:

- One vault path per shared resource (`streck/secrets/lab-ops-db`,
  `streck/secrets/mail-relay`, `streck/secrets/ado-pat`).
- Consumers reference by path, not by copy. Rotation is one-touch.
- `compliance_flags` containing `phi` forces `phi`-annotated vault
  paths (extra logging on access).
- `portfolio-architect` emits a vault-paths manifest as part of its
  shared-infra proposal.

### P10. Portfolio-level compliance policy

`compliance_flags` is a per-intake field today. At the portfolio
level we need the union:

- `Portfolio.compliance_union` is computed from `intakes[*].compliance_flags`.
- `subagent_start.py` (today: reads `.soup/intake/active.yaml` for
  one intake's flags) grows a fallback: if the active run belongs
  to a portfolio, load `.soup/portfolio/active.yaml` and union the
  compliance flags across all member intakes that overlap with the
  current step's `spec_refs`.
- Example: when a step implements a **shared** Postgres reader
  consumed by both a `lab-data`-only intake and a `phi`-flagged
  intake, the step must operate under `phi` rules (strictest
  wins). Today soup has no mechanism to know that.

## How this pairs with iter-2 compliance

Iter-2's intake-form report (iter2-intake-form.md §"Simulated flow
walkthrough") established that `compliance_flags` is the lever that
converts intake metadata into runtime rules — `subagent_start.py`
reads `.soup/intake/active.yaml`, extracts `compliance_flags[]`, and
appends `rules/compliance/<flag>.md` to each subagent's
`additionalContext`.

Multi-intake breaks the one-active-intake assumption in three ways
this report must address:

1. **One step can serve N intakes.** If the
   `shared-lib/python-postgres-reader` scaffold step (P5) is
   consumed by both the `lab-data`-flagged pipette-dashboard and
   the `phi`-flagged sample-intake-receiver, the step runs under
   the **union** of both flag sets — `phi` wins (strictest
   overrides least-strict). P10 codifies this as the "strictest
   wins" rule at the portfolio level.
2. **Audit-log obligations compound.** `lab-data` triggers a
   7-year retention reminder (iter2 §bucket 4). Across 5 intakes
   with overlapping schemas (apps #1, #2, #3 all write into
   `lab-ops-db`), we need **one** audit-log table, not three — and
   `portfolio-architect` must propose that in the shared-infra
   pass (P2). Otherwise each app spins up its own `edit_audit_entry`
   schema (see `asset-inventory-lite.yaml:54`) and compliance
   discovers the drift at audit time.
3. **Public ⊥ sensitive at the sprint level.** Iter-2 enforces
   this as a per-intake validator
   (`_flags_are_consistent`, `intake_form.py:202`). At the
   portfolio level the PM might have two apps that individually
   pass but collectively share infra that must not straddle the
   boundary: a `public` app and a `phi` app cannot share a vault
   path or a Postgres cluster. P3's `Portfolio` validator lifts
   the iter-2 rule to the sprint level.

Put differently: the iter-2 report built the hook that reads **one**
intake's compliance flags. Multi-intake forces an upgrade from
"whose flags does this subagent see?" to "what is the union of flags
across everything this subagent's work is consumed by?" The answer
is the portfolio, not any single intake.

## Summary of new artefacts (reference)

| Artefact | Type | Owner |
|---|---|---|
| `/intake --batch <dir>` | command | `.claude/commands/intake.md` (extended) |
| `portfolio-architect` | agent | `.claude/agents/portfolio-architect.md` |
| `schemas/portfolio.py::Portfolio` | Pydantic model | `schemas/portfolio.py` |
| `orchestrator/portfolio.py` | module | `orchestrator/portfolio.py` |
| `templates/shared-lib/*` | template tier | `templates/shared-lib/` |
| `soup portfolio budget / cost` | CLI | `orchestrator/cli.py` (extended) |
| `/portfolio-report` | command | `.claude/commands/portfolio-report.md` |
| `rules/patterns/shared-postgres-reader.md` | rule | new |
| `rules/patterns/shared-secrets-vault.md` | rule | new |
| `.soup/portfolio/active.yaml` + `.soup/portfolio-runs/` | runtime state | orchestrator/portfolio.py |
| `subagent_start.py` union-of-flags mode | hook upgrade | existing file |

All additive. The single-intake path (iter-2) remains the canonical
80%-case entry point. The portfolio layer wraps, it does not replace.
