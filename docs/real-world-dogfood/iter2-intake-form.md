# Iteration 2 dogfood — intake-form-driven greenfield

**Date:** 2026-04-14
**Mode:** Simulated greenfield-from-intake (no real apps scaffolded).
**Subject:** the new `/intake` flow, exercised against
`intake/examples/pipette-calibration-dashboard.yaml` and
`intake/examples/asset-inventory-lite.yaml`.

This report is the design rationale for `schemas/intake_form.py`,
`intake/examples/*`, and `.claude/commands/intake.md`, plus a walk-
through of the full pipeline they unlock. It complements iter-1's three
dogfood reports (`middle-earth-app.md`, `claude-news-aggregator.md`,
`warhammer-40k-calculator.md`), which all surfaced the same headline
gap: **soup has no canonical onboarding artefact for a brand-new
internal app**. `/intake` is that artefact.

## Intake form design rationale

Iter-1 surfaced three recurring intake problems:

1. **`/specify` over-specs existing contracts.** The
   claude-news-aggregator report flagged that asking `spec-writer` to
   restate a contract that already lives in `plan/v3-final.md` is a
   wasted round-trip. For new apps the inverse problem appears: there
   *is* no contract yet, and `spec-writer` has no structured way to
   ask "what are your inputs / outputs / integrations?" It either
   guesses or punts to `/clarify`.

2. **Project specifics never reach specialist subagents.** The
   warhammer-40k-calculator report identified
   "project-specific agent briefs that carry domain knowledge" as the
   one thing the warhammer repo did better than soup. Soup's
   `TaskStep.prompt` is too thin for meaty work; the iter-1 fix added
   `context_excerpts` / `spec_refs`, but those are only useful if the
   spec **has** the relevant domain content captured in named
   anchors. An intake form is the upstream forcing-function for that.

3. **Cross-stack contracts are blind spots.** The middle-earth-app
   report (Supabase contract drift) and warhammer (OpenAPI ↔ TS
   types) reports converge on the same finding: integration
   boundaries are where soup most needs structured metadata. Free-
   text specs produce free-text integration descriptions which
   produce free-text task prompts which produce contract drift.

`IntakeForm`'s shape is a direct response. The fields fall into four
buckets, each matched to a soup pain-point:

| Bucket | Fields | Pain point addressed |
|---|---|---|
| **Identity** | `app_slug`, `app_name`, `description`, `intent`, `requesting_team` | Drives `specs/`, `.soup/plans/`, sibling app dir names. The kebab-case validator (`_SLUG_PATTERN`) prevents the inconsistent-naming tax (warhammer report's `AGENT_*_SPEC.md` vs `*_AGENT_*_STATUS.md` confusion). |
| **Behaviour** | `primary_users`, `inputs`, `outputs`, `success_outcomes`, `constraints` | Maps 1-for-1 onto `spec-writer`'s 7 required sections. Removes the "what does the user actually do?" clarify round-trip. |
| **Boundaries** | `integrations` (kind/ref/purpose/auth) | Each integration becomes one `## Integrations` row + one EARS REQ + one downstream `context_excerpts` hint. This is the missing structured input that contract-drift bugs need. |
| **Routing** | `stack_preference`, `deployment_target`, `compliance_flags`, `deadline` | Drives `/soup-init` template choice, `/plan`'s architect pre-pass decision, security-scanner severity floor, and timeline bracketing. Kept **out** of the spec (Article I — what, not how). |

Two design decisions worth flagging:

- **`stack_preference` lives on the form, not the spec.** Article I
  says specs describe *what*, not *how*. But the team that requests an
  app does have a stack opinion, and forcing them to suppress it until
  `/plan` runs is dishonest. The form captures it; `/intake` writes it
  to a stashed `.intake.yaml` next to the spec; `/plan` reads it.
  Spec stays clean.
- **`compliance_flags` triggers behaviour without being in the spec
  body.** `pii`/`phi`/`financial` raise the security-scanner severity
  floor; `lab-data` adds the 7-year retention reminder. The mutual-
  exclusivity validator (`public` ⊥ {`internal-only`,`pii`,`phi`,
  `financial`}) catches the most common intake mistake: a team
  ticking "public" on an internal compliance dashboard.

## Simulated flow walkthrough — pipette-calibration-dashboard

Walking
`intake/examples/pipette-calibration-dashboard.yaml` (5 integrations,
4 inputs, 5 outputs, `lab-data` + `internal-only`,
`fullstack-python-react`) through the full pipeline. **No real
artefacts written** — this is a paper trace.

### Step 1 — `/intake --file intake/examples/pipette-calibration-dashboard.yaml`

- **Parse + validate.** `IntakeForm.from_yaml(path)` succeeds (proven
  empirically — `python -c "from schemas.intake_form import IntakeForm;
  IntakeForm.from_yaml('intake/examples/pipette-calibration-dashboard.yaml')"`
  returns a model with `len(integrations)=5`).
- **Slug + collision check.** `specs/pipette-calibration-dashboard-2026-04-14.md`
  does not exist. Proceed.
- **Invoke `spec-writer` (Mode B).** Pass the parsed `IntakeForm` to
  the agent. The agent:
  - Renders `## Summary` from `description` + `intent`.
  - Renders `## Stakeholders & personas` from `primary_users` (3 rows).
  - Renders `## User outcomes` from `intent` framing + `success_outcomes`.
  - Renders 9 EARS requirements under `## Functional requirements`
    (4 inputs + 5 outputs).
  - Renders `## Non-functional requirements` from `constraints` (4
    rows: P95 load, VPN-only, engineer budget, retention) + the
    `lab-data` audit-log obligation.
  - Renders `## Acceptance criteria` from `success_outcomes` verbatim
    (4 testable lines).
  - Renders `## Out of scope` with the deadline ("everything past
    2026-06-14 is a follow-up").
  - Renders `## Integrations` as a 5-row table.
- **Save.** `specs/pipette-calibration-dashboard-2026-04-14.md`.
- **Stash.** `specs/pipette-calibration-dashboard-2026-04-14.intake.yaml`
  (copy of the validated form).
- **Routing hint.** `len(integrations) == 5 >= 3` → suggest
  `/plan --architect-pre-pass`. The form has `success_outcomes`
  mentioning "audit log" alongside `lab-data`, so no `/clarify`
  required for compliance.

### Step 2 — `/plan --architect-pre-pass`

- **Spec resolution.** Newest `specs/*.md` with no open questions →
  `pipette-calibration-dashboard-2026-04-14.md`. Spec freezes here
  (Article I.4).
- **Architect pre-pass (read-only).** Per `architect.md` "Boundaries
  — modules, interfaces, data contracts (cite schemas)" red flag,
  the pre-pass walks each `## Integrations` row and produces:
  - `AssetTracker REST` — read-only client; cache TTL 5 min in
    Postgres; rate-limit handling; circuit-breaker fallback to cached
    rows.
  - `ADO project streck/LabOps` — read-only `cli_wrappers/ado.py`
    wrapper; query work-items by `Streck.AssetId` custom field; auth
    via PAT in env `ADO_PAT`.
  - `streck/lab-design-system` GitHub repo — pinned npm dep on
    `@streck/lab-design-system@^2`; build pulls private package via
    `cli_wrappers/git.py` + `gh.py`.
  - `lab_ops` Postgres — owned schema; alembic migrations in
    `migrations/`; `sql-specialist` sole author.
  - Mail relay REST — POST-only; idempotency key on
    `subject+date+recipient`; retry-with-jitter; dead-letter to
    Postgres on >3 failures.
- **`plan-writer`.** Reads architect output + spec. Emits
  `.soup/plans/pipette-calibration-dashboard.md` with the canonical
  10 sections. `## File map` annotates each path with its spec
  anchor (e.g. `app/services/asset_tracker.py -- implements specs/pipette-calibration-dashboard-2026-04-14.md#integrations`).
- **Tech choices** land on `fullstack-python-react`:
  Python/FastAPI + React+TS + Postgres + Docker. Honors the form's
  `stack_preference` without re-debating.
- **Estimated `budget_sec`:** ~14400 (4h walk; 5 integrations × ~30
  min + ~2h shared infra + ~2h frontend + ~2h tests).

### Step 3 — `/tasks`

`tasks-writer` reads the markdown plan and emits ~22 steps:

- 1 schema/migration step (`sql-specialist`, `migrations/0001_initial.sql`).
- 5 × (`test-<I>` + `impl-<I>`) integration adapter pairs (3 REST + 1
  ADO + 1 GitHub-build = `python-dev`).
- 2 × (`test-<C>` + `impl-<C>`) cache + audit-log domain services
  (`python-dev`).
- 4 × (`test-<R>` + `impl-<R>`) FastAPI routes
  (`/api/v1/pipettes`, `/api/v1/export.csv`, `/api/v1/filters`,
  `/api/v1/audit`).
- 3 × (`test-<F>` + `impl-<F>`) React frontend pieces (table view,
  status card, CSV trigger button) — `react-dev`.
- 1 cross-stack `full-stack-integrator` step verifying OpenAPI ↔ TS
  types match.
- 1 `verifier` step running `pytest` + `vitest` + smoke.

Every `impl-<I>` step where the prompt references an integration
boundary should carry `context_excerpts: ["specs/pipette-calibration-dashboard-2026-04-14.md#integrations"]`.
**Friction:** `tasks-writer.md` documents the convention but the
agent has to **infer** which steps touch the integrations section
from the plan markdown. There is no link from "this task implements
asset_tracker.py" → "asset_tracker.py implements integration #1".
See gap G3.

### Step 4 — `/implement`

`orchestrator` computes waves:

- Wave 1: `S1-test-migration` + the 3 in-parallel test stubs for
  AssetTracker / ADO / GitHub adapters (no shared files).
- Wave 2: implementation of those + frontend test stubs in parallel.
- Wave N: full-stack-integrator + verifier.

Atomic commits per step; QA gate (Stop hook → `qa-orchestrator`)
fans out to `code-reviewer`, `security-scanner`, `verifier`. The
`security-scanner` honors the `lab-data` flag and rejects any code
that logs raw asset data without redaction.

### Step 5 — `/verify`

Verifier runs all `verify_cmd`s declared in the plan + `just test` if
present. The `fullstack-python-react` template ships a `justfile` —
this works. (Iter-1 noted that `verifier` hard-codes `just test` as a
fallback, which still bites repos without a justfile; not a new gap.)

## Friction points found

The simulated flow exposes these specific snags:

1. **`spec-writer.md` Mode B section list ≠ `/specify.md` 7-section
   list.** Mode B legitimately adds `## Integrations`; the agent card
   now documents it as an optional eighth section. `/intake` and
   `/specify` both read the same agent card, so they stay in sync.
   But the orchestrator's downstream agents that *consume* the spec
   (`plan-writer`, `tasks-writer`) do not have a spec section
   schema — they grep by header. Adding/removing an optional section
   is a quiet contract change.

2. **Stashed `.intake.yaml` has no consumer.** `/intake` writes it
   next to the spec for audit and for `/plan` to read tech choices
   from, but no current command actually reads it. `/plan` would need
   to know to look for `specs/<slug>-<date>.intake.yaml` to honor
   `stack_preference`. Today the architect would re-derive the stack
   from prose in `## Summary`, which is brittle.

3. **`tasks-writer` cannot link adapter implementations back to the
   `## Integrations` table.** The plan markdown's `## File map` annotates
   *spec sections*, but the integrations live in a single section. So
   every adapter step gets the same `context_excerpts: [...#integrations]`
   — fine for the small case, but for the pipette example the
   specialist subagent loads all 5 integration descriptions when it
   only needs one. Need finer-grained anchors per integration row
   (e.g. `#integration-asset-tracker-rest`).

4. **No "intake → architect pre-pass" wiring.** `/intake` *suggests*
   `/plan --architect-pre-pass`, but the `--architect-pre-pass` flag
   does not actually exist in `/plan.md`. The intake command writes a
   prose hint; the operator has to remember to type it. Should be
   either an actual `/plan` flag or auto-routed by counting
   integrations in the spec.

5. **`compliance_flags` route through prose only.** The intake form
   captures `lab-data` + `internal-only` as enums, but the spec
   renders them as a paragraph and Postgres rules consume them via
   string match. `security-scanner` should read the stashed intake
   YAML directly to know "this app is `lab-data`; raise SQL-injection
   findings to critical."

6. **The new `## Integrations` section is invisible to
   `/clarify`.** `/clarify` walks `## Open questions`. If an
   integration has `auth: tbd`, that should automatically become an
   open question — but today `/intake` would have to seed
   `## Open questions` with "What auth for AssetTracker REST?" and
   the connection to the integration row is implicit.

7. **`nextjs-app-router` template fit.** The pipette example uses
   `fullstack-python-react`, which fits cleanly. For an
   `nextjs-app-router` intake (e.g. a marketing-adjacent internal
   site), the template *exists* (added in iter-1 per the middle-
   earth-app report), but the form has no field to capture the
   "Server Component vs Client Component" preference that the
   nextjs-app-router rules (`rules/nextjs/app-router.md`) demand.
   Forms that target Next.js need a `nextjs_routing_strategy: server-
   first | client-heavy | hybrid` field.

8. **No persona-to-route mapping.** `primary_users` is a flat list
   ("Lab Tech", "Lab Ops Manager", "QA Compliance Auditor"). Three
   personas often want three different views of the same data; the
   spec would benefit from one page per persona, but `/intake` cannot
   express that today. Could add `views: list[ViewSketch]` linking
   personas to outputs.

## Soup gaps (concrete)

1. **G1 — `/plan` does not read stashed `.intake.yaml`.** Add a
   resolution step in `/plan.md` ("if `specs/<slug>-<date>.intake.yaml`
   exists, load it and surface `stack_preference` /
   `deployment_target` to the architect prompt"). Without this, the
   form's stack hint is lost between commands.

2. **G2 — No `/plan --architect-pre-pass` flag.** `/intake` suggests
   it; `/plan.md` does not implement it. Either add the flag (a
   distinct workflow that runs `architect` twice — once on
   integrations, once on the rest) or auto-trigger it when
   `len(integrations) >= 3`. A heuristic in `/plan.md` ("if the spec
   has a `## Integrations` table with ≥3 rows, run the pre-pass") is
   the cheapest fix.

3. **G3 — Per-integration anchors in the spec.** The
   `## Integrations` table is one anchor (`#integrations`). Refactor
   `spec-writer` Mode B to emit one anchor per integration row
   (`#integration-asset-tracker-rest`, ...) so `tasks-writer` can
   inject finer-grained `context_excerpts` per task. Without this,
   every adapter step loads the full integrations table.

4. **G4 — `compliance_flags` should drive injected rules, not just
   prose.** Add a `pre_tool_use` hook (or a `subagent_start` injection)
   that reads the stashed `.intake.yaml`, finds `compliance_flags`,
   and prepends matching rule files (`rules/compliance/lab-data.md`,
   `rules/compliance/pii.md`) to specialist subagent prompts. This is
   the most leveraged of the gaps — it operationalises a field that
   would otherwise be decorative.

5. **G5 — Auto-seed `## Open questions` from `auth: tbd` integrations.**
   When an `Integration.auth == "tbd"` is in the form, `/intake`
   should automatically add the corresponding question to
   `## Open questions` so `/clarify` can address it before `/plan`.
   Today this is on the human.

6. **G6 — No `intake/<app_slug>.yaml` discovery in `/specify`.** If a
   user runs `/specify "build a pipette dashboard"` and an
   `intake/pipette-calibration-dashboard.yaml` exists, `/specify`
   should detect the slug overlap and route them to `/intake`. Today
   they will produce a parallel free-text spec that diverges from
   the form.

7. **G7 — No "interactive intake" UI.** The `/intake.md` workflow
   says "fall back to interactive via `AskUserQuestion`", but
   `AskUserQuestion` does not handle structured nested objects (lists
   of integrations). For the interactive flow, soup needs a
   `tools/intake_wizard.py` (Typer CLI) that walks the form and
   serialises YAML, invoked from `/intake` when no `--file` is
   provided.

8. **G8 — Form versioning.** `IntakeForm` will evolve (e.g. adding
   `nextjs_routing_strategy` per friction point 7). There is no
   `schema_version` field on the form — adding fields tomorrow
   breaks every stashed `.intake.yaml` from today. Add
   `schema_version: int = 1` with a migration helper.

9. **G9 — `requesting_team` is captured but unused.** No agent reads
   it. At minimum it should appear in the `qa_report` "owner" field
   so QA findings get routed to the right team. Today the form
   captures the field and discards it post-spec.

10. **G10 — No way to declare "this is a dependency on an existing
    soup-built app."** When the pipette dashboard depends on, say,
    an existing `streck/lab-portal` app (also built by soup), the
    form has no kind for it. Add `kind: soup-app` so the architect
    can read sibling specs/plans rather than treat it as a black-box
    REST endpoint.

## Ergonomic wins

What works in the new flow:

- **YAML readability.** The pipette example is ~150 lines; reviewing
  it in a PR is fast. Block scalars (`>`/`|`) keep multi-paragraph
  fields diff-friendly.
- **One forcing function for project-specific knowledge.** The
  iter-1 reports converged on "soup needs a way for project
  knowledge to reach specialist subagents." The intake form is the
  upstream catch-net: every field maps to either spec content (which
  reaches `tasks-writer`) or routing (which reaches the architect).
- **Validator-first.** `IntakeForm.from_yaml` rejects 5 classes of
  errors at parse time — bad slugs, bad dates, conflicting
  compliance flags, unknown enum values, missing required fields. No
  half-validated form ever reaches `spec-writer`.
- **Spec stays clean.** Tech / deployment / team-routing are kept
  out of the spec body and stashed in `.intake.yaml` instead.
  Article I (what-not-how) is preserved.
- **Mode A unchanged.** Free-text `/specify "..."` is untouched.
  Adding `/intake` is purely additive — engineers who like the old
  flow keep it.
- **Cross-link in `/specify.md`.** A two-paragraph block points new
  apps to `/intake` without forcing it. Lower friction than a hard
  redirect.
- **Compliance enums catch the easy mistakes.** The `public` ⊥
  `internal-only`/PII/PHI/financial validator caught 1 of 4 real
  examples I drafted before settling on the published two — that is
  exactly the failure mode the form is meant to filter.
- **Realistic example informs the schema.** Designing
  `pipette-calibration-dashboard.yaml` and `asset-inventory-lite.yaml`
  in tandem with the schema surfaced two sub-shapes (`IntakeField`
  reused for inputs+outputs; `Integration.auth` as enum not string)
  that wouldn't have appeared from schema-first design.

## Proposed next-iteration additions

For iter-2's improvement agents (in priority order):

1. **`rules/compliance/{lab-data,pii,phi,financial}.md`** + a hook
   that injects them based on the stashed `.intake.yaml`'s
   `compliance_flags` (G4). Highest leverage — operationalises a
   field that is otherwise decorative.

2. **`/plan` reads `.intake.yaml`** for `stack_preference` /
   `deployment_target` / `compliance_flags` (G1). One-paragraph
   change in `/plan.md` plus a glob in the workflow.

3. **`spec-writer` Mode B emits per-integration anchors** in the
   `## Integrations` table (G3). Lets `tasks-writer` carry only the
   one integration any given step needs.

4. **`/plan --architect-pre-pass` becomes real** or auto-fires when
   `len(integrations) >= 3` (G2). Either is fine; auto-fire is less
   work.

5. **`tools/intake_wizard.py` Typer CLI** (G7) for interactive
   intake without depending on `AskUserQuestion`. Writes a valid
   YAML then exits.

6. **`schema_version: int = 1` field on `IntakeForm`** + a
   `migrate_intake.py` helper (G8). Forward-compat insurance before
   the form ships beyond two examples.

7. **`Integration.kind == "soup-app"`** (G10). Cross-app dependencies
   are a near-term reality once Streck has 3+ soup-built apps; the
   form should express it now.

8. **Auto-seed `## Open questions` from `auth: tbd`** in `/intake`
   (G5). Mechanical change in the command.

9. **`requesting_team` flows into `QAReport.owner`** (G9). Connect
   the dot from form to QA so blocked findings route correctly.

10. **`nextjs_routing_strategy` field** for nextjs-app-router
    intakes (friction point 7). Optional; defaults to `server-first`.

These ten changes together turn `/intake` from a shape-validator into
a load-bearing routing artefact — every field on the form does
work somewhere downstream. As shipped today, fields 5-9 of `IntakeForm`
already do work; fields 10-15 are decorative until the above land.

## Files written by this iteration

- `schemas/intake_form.py` — the new schema (165 LOC, 9 enums,
  cross-field validator).
- `tests/test_intake_form.py` — 44 tests, all passing.
- `intake/examples/pipette-calibration-dashboard.yaml` — realistic
  5-integration example.
- `intake/examples/asset-inventory-lite.yaml` — 2-integration
  reference example.
- `intake/README.md` — operator-facing field reference.
- `.claude/commands/intake.md` — the new command.
- `.claude/agents/spec-writer.md` — added Mode B (structured intake)
  with field-to-section mapping and `## Integrations` rendering.
- `.claude/commands/specify.md` — cross-link to `/intake`.
- `docs/real-world-dogfood/iter2-intake-form.md` — this report.

No app was scaffolded; no spec was written; no plan was committed.
The simulation walked the pipeline on paper using only the new
artefacts above.
