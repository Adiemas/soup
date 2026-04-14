---
description: Convert plan markdown into TDD-shaped ExecutionPlan JSON (failing-test task before each impl task). Validated by schemas/execution_plan.py.
argument-hint: [plan-path]
---

# /tasks

## Purpose
Formalize a plan's task outline into a runnable `ExecutionPlan` validated by `schemas/execution_plan.py::ExecutionPlan`. Output is what `/implement` consumes.

## Variables
- `$ARGUMENTS` — optional plan path; defaults to most recent `.soup/plans/<slug>.md`.

## Workflow
1. Resolve plan path. Default: newest `.soup/plans/*.md`. If multiple newest candidates exist (same mtime), abort and AskUserQuestion for disambiguation.
2. Invoke `tasks-writer` (sonnet) with a structured instruction:
   - Read the markdown plan; consult `library.yaml` for valid agent names.
   - For every implementation task T in `## Task outline`, emit TWO steps:
     1. `test-<T>` — `test-engineer` agent; `verify_cmd` asserts non-zero exit (red).
     2. `impl-<T>` — specialist by stack (`python-dev`, etc.), `depends_on: ["test-<T>"]`; `verify_cmd` runs the test expecting pass (green).
   - Each step: `files_allowed` (glob), `model`, `max_turns <= 10`, `parallel` where deps allow.
   - Emit ONLY JSON matching `ExecutionPlan` schema. No prose, no fences.
3. Validate via `soup plan-validate <path>` (preferred) or fall back to
   `python -c "from schemas.execution_plan import ExecutionPlan, ExecutionPlanValidator; p = ExecutionPlan.model_validate_json(open('<path>').read()); ExecutionPlanValidator.from_library('library.yaml').validate(p)"`.
   On failure, feed the error back to `tasks-writer` and retry up to 3x.
4. Save to `.soup/plans/<slug>.json`.

## Output
- Plan JSON path.
- Step count (test / impl breakdown).
- Estimated budget_sec.
- Validation status.
- Next step: `/implement`.

## Notes
- The markdown plan (`.soup/plans/<slug>.md`) is authored by `plan-writer` and left untouched.
- The JSON is authored by `tasks-writer` — same basename, `.json` extension. They coexist; `/implement` reads the JSON.
- No impl step without a preceding failing-test step. TDD iron law.
- Steps exceeding 10 turns are rejected at validation time.
- Agent names must match `library.yaml` roster (enforced by field validator on `TaskStep.agent`).
- **Migration routing:** any step whose `files_allowed` matches `**/Migrations/**` or `**/*.sql` **must** be assigned `agent: sql-specialist` (Constitution V.1). For EF Core, `dotnet-dev` scaffolds the C# migration class via `cli_wrappers.dotnet ef-migrate` and `ef-script`, then hands off the `.up.sql` / `.down.sql` pair and the `Up()`/`Down()` bodies to `sql-specialist` for review and commit. See `.claude/agents/sql-specialist.md` for the ownership table.
- **Utility agents in `library.yaml`:** `git-ops`, `doc-writer`, `docs-scraper`, `researcher` are valid agent names — use them for commit plumbing, prose, and RAG-style research steps.
- **Context preservation** (`schemas/execution_plan.py::TaskStep.context_excerpts` / `spec_refs`): `tasks-writer` SHOULD set `context_excerpts` and `spec_refs` on every step where the specialist will need project-specific domain knowledge that does not belong in the shared roster prompt. Rules of thumb:
  - Any step whose `prompt` references a formula, oracle value, or contract shape that lives in the spec -> add `spec_refs: ["specs/<name>.md"]`.
  - Any step that implements or modifies a specific section of a larger spec -> add `context_excerpts: ["specs/<name>.md#<section-anchor>"]` so the subagent sees only the relevant slice (cheaper than loading the whole spec).
  - Any step that must preserve a code-level contract (e.g. an interface, a Pydantic model, a SQL table DDL) -> add `context_excerpts: ["<path>:<line_from>-<line_to>"]`.
  - Paths must be relative to the repo root; absolute paths are rejected at parse time. `ExecutionPlanValidator` rejects plans whose referenced paths do not exist — so author these fields only after the source artifacts are committed.
  - `agent_factory.spawn` resolves and injects these excerpts once at brief-compose time; the subagent receives them under a `## Context excerpts (verbatim)` section in its first-turn prompt and does not need to `Read` the source files itself.
- **Per-integration anchors** (when the spec was emitted by `/intake` Mode B):
  the `## Integrations` section carries one `### <kind>: <ref>` subsection per
  integration with a deterministic anchor slug
  (`#integration-<kind>-<ref-slug>`, e.g.
  `#integration-rest-api-assettracker-streck-internal` — see
  `.claude/agents/spec-writer.md` for the slug algorithm).
  `tasks-writer` SHOULD use these finer-grained anchors rather than the
  single `#integrations` anchor when a step touches a specific integration
  boundary:
  - An adapter impl step for AssetTracker REST → `context_excerpts:
    ["specs/<slug>.md#integration-rest-api-assettracker-streck-internal"]`
  - A contract test for the same integration → same anchor in
    `context_excerpts`.
  - The shared-across-integrations scaffolding step (e.g. the base HTTP
    client) → the plain `#integrations` section anchor is still correct
    (because the step reads all rows).
  This prevents specialist subagents from loading the full integration
  table when they only need one integration's slice.
- **Compliance flags on `ExecutionPlan`** (intake-YAML-driven): when an
  intake YAML is present at `specs/<slug>-<date>.intake.yaml`,
  `tasks-writer` SHOULD propagate its `compliance_flags[]` onto the
  `ExecutionPlan` JSON so the orchestrator can echo them on every
  spawn and so downstream reviewers (security-scanner) can raise their
  severity floor. **Coordination note:** the `ExecutionPlan.compliance_flags`
  field is being introduced by iter2-improve γ in `schemas/execution_plan.py`.
  If the schema has not yet been updated when you run `/tasks`, fall back
  to recording the flags in the `ExecutionPlan.notes` field as
  `"compliance_flags: [<flag>, ...]"` so the information is not lost; the
  orchestrator's `additionalContext` path will pick them up from the
  stashed intake YAML directly via `subagent_start.py` regardless.
