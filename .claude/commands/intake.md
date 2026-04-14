---
description: Greenfield-from-intake or brownfield-from-repo. Validate a Streck intake YAML form (and/or research an existing repo), render a spec, and emit next-step routing.
argument-hint: "[--file <path-to-intake.yaml>] [--brownfield <existing-repo-path>] | (interactive)"
---

# /intake

## Purpose

Author a brand-new internal app (or an extension against an existing
repo) from a **structured intake form** + optional **researcher
pre-pass** rather than a free-text `/specify` goal. The form removes a
clarify round-trip, pre-populates the spec's `## Integrations` section,
and threads each integration into downstream `TaskStep.context_excerpts`
hints so specialist subagents see contract excerpts without
re-discovering them.

For a free-text idea on an existing app, keep using
[`/specify`](specify.md). `/intake` is the canonical entry point for
**new** Streck apps and for brownfield extensions that need a
researcher pre-pass; `/specify` remains available for quick iteration.

## Variables

- `--file <path>` — path to the YAML intake form (e.g.
  `intake/examples/pipette-calibration-dashboard.yaml`). Optional; if
  omitted **and** `--brownfield` is also omitted, the command falls
  back to the interactive flow below.
- `--brownfield <repo-path>` — absolute or relative path to an
  existing Streck repository this app extends. When set, the
  `researcher` utility agent runs BEFORE `spec-writer` and produces a
  findings table the spec-writer references via `spec_refs`. Mutually
  compatible with `--file`: you can pass both (form-driven spec with
  researcher-anchored integration context) or either alone.
- `$ARGUMENTS` — anything else after the flags is ignored.

## Workflow

1. **Parse flags.** Extract `--file <path>` and/or
   `--brownfield <repo-path>`. Both optional. At least one of
   `--file`, `--brownfield`, or the interactive fallback must provide
   the agent with something to work from.

2. **Resolve form input (if `--file` given).**
   - Read and parse with
     `schemas.intake_form.IntakeForm.from_yaml(path)`.
   - On `ValidationError`, print the offending field path + error and
     abort. **Do not** silently default missing fields — the iron law
     for `/intake` is "no spec without a valid form."
   - **Auto-prompt for `--brownfield`.** Inspect
     `form.integrations[]`. If any integration has
     `kind == "github-repo"` or `kind == "ado-project"` and its `ref`
     resolves to an on-disk path (or the heuristic suggests it might —
     `streck/...` repo slugs, local clones under common roots), call
     `AskUserQuestion` to propose: "integration `<ref>` looks like an
     existing repo. Re-run with `--brownfield <path>` for a researcher
     pre-pass?" Accept `yes/no/other-path`. If the user accepts, add
     `--brownfield <path>` to the effective flags and continue. If the
     user declines, proceed without the pre-pass.

3. **Resolve interactive input (if no `--file`).** Drive an
   interactive flow via `AskUserQuestion`. Walk the user through the
   field reference in
   [`intake/README.md`](../../intake/README.md) — one question per
   section (identity → users → inputs → outputs → integrations →
   stack/deployment → outcomes → constraints → compliance), then write
   the captured answers to `intake/<app_slug>.yaml` so the intake
   artefact is preserved alongside the spec. Validate via
   `IntakeForm.from_yaml` before proceeding (same iron law).

4. **Slug + collision check.** Refuse to proceed if
   `specs/<app_slug>-<YYYY-MM-DD>.md` already exists. If a prior dated
   spec for the same slug exists, route the user to `/specify` for the
   next-version flow (Constitution I.4 — specs are frozen) and exit.
   If no `--file` was given (brownfield-only mode), derive the slug
   from the repo's directory name (`basename <repo-path>`) and run the
   same collision check.

5. **Run researcher pre-pass (if `--brownfield` set).** Dispatch the
   `researcher` utility agent (haiku; see
   `.claude/agents/utility/researcher.md`) with a brief shaped like:

   > Target repo: `<repo-path>`.
   > Task: "Enumerate the repository's structure, entry points,
   > existing external contracts (OpenAPI, protobufs, RPC schemas),
   > and ADRs filed in the last 90 days. Produce the standard findings
   > table (`file | line | relevance | excerpt`) and a short
   > `## Summary`. Mark any file whose contract this new feature will
   > extend as `relevance = primary`."

   Save the researcher output to
   `.soup/research/<slug>-findings.md`. If the researcher returns no
   findings (empty table), abort `/intake` — the pre-pass is
   load-bearing for downstream `context_excerpts` hydration and an
   empty table indicates the repo path was wrong or the agent
   exhausted its search budget on the wrong surface. Ask the user to
   re-run with a scoped `--brownfield <sub-path>`.

6. **Invoke `spec-writer` with structured input.** Pass the
   spec-writer agent:
   - If `--file` provided: the parsed `IntakeForm` (Mode B — the
     structured-intake flow documented in
     [`.claude/agents/spec-writer.md`](../agents/spec-writer.md)).
   - If `--brownfield` provided: the path
     `.soup/research/<slug>-findings.md` as additional context, to be
     cited in the spec's `spec_refs`. The spec-writer MUST include a
     `## Brownfield notes` section listing the parent repo + the
     researcher findings path when the pre-pass ran.
   - If **both** provided: form + findings. The form drives spec
     content; the findings drive `spec_refs` and
     `## Integrations` concretisation (each integration row gets a
     `source` link pointing at the researcher's file/line anchor when
     the researcher found the existing contract).

   Field-to-section mapping (Mode B):

   | Intake field | Spec section |
   |---|---|
   | `description` | `## Summary` |
   | `intent` | `## Summary` (intent paragraph) + `## User outcomes` framing |
   | `primary_users` | `## Stakeholders & personas` |
   | `inputs` + `outputs` | `## Functional requirements` (one EARS REQ per field) |
   | `success_outcomes` | `## Acceptance criteria` (verbatim — must be testable) |
   | `constraints` | `## Non-functional requirements` |
   | `compliance_flags` | `## Non-functional requirements` (security/audit obligations) and a top-of-spec banner |
   | `integrations` | new `## Integrations` section — one `### <kind>: <ref>` subsection per integration (see §Per-integration anchors below) |
   | `deadline` | `## Out of scope` (anything that cannot fit) |
   | `stack_preference` / `deployment_target` | **NOT** included in the spec — passed forward to `/plan` only via the stashed intake YAML |

7. **Per-integration anchors.** When `integrations[]` is non-empty,
   the `## Integrations` section MUST emit one `### <kind>: <ref>`
   subsection per integration with a deterministic anchor slug so
   downstream `tasks-writer` can cite one integration at a time (e.g.
   `#integration-asset-tracker-rest`) rather than loading the full
   table. See
   [`.claude/agents/spec-writer.md`](../agents/spec-writer.md) for the
   canonical slug derivation (`kind + ref`, kebab-case, collisions
   resolved by numeric suffix).

8. **Save the spec.** `specs/<app_slug>-<YYYY-MM-DD>.md`. Echo the
   path.

9. **Stash the form (the audit trail + planner input).**
   - Copy the validated intake YAML to
     `specs/<app_slug>-<YYYY-MM-DD>.intake.yaml` (frozen, travels with
     the spec, per Constitution I.4). The original
     `intake/<app_slug>.yaml` is left untouched (humans edit it; the
     dated `.intake.yaml` is the audit trail).
   - Also write a **symlink-free copy** to `.soup/intake/active.yaml`
     so hooks (`subagent_start.py`) can find the most recent intake
     without needing a slug parameter. `active.yaml` is replaced on
     every `/intake` invocation — treat it as a pointer, not a
     history. The dated `.intake.yaml` under `specs/` is the history.

   Write order: stash to `specs/` first, then overwrite
   `.soup/intake/active.yaml`. If the copy step fails (permissions,
   disk), do not leave `active.yaml` stale — roll it back (the
   previous file is fine) and surface the error.

10. **Route to next step.** Print one of:
    - `/plan` — single stack, fewer than 3 integrations, greenfield.
    - `/plan --architect-pre-pass` — `len(integrations) >= 3`. The
      architect needs an extra read-only pass to lay out the
      integration boundary contracts before `plan-writer` decomposes
      tasks. (See `architect.md` red flags — designs that don't name
      contracts are rejected.)
    - `/plan` — brownfield (researcher findings already populate
      integration anchors; architect's pre-pass job is reduced).
    - `/clarify` first — only if `compliance_flags` includes `pii`,
      `phi`, or `financial` AND no audit-log mention exists in
      `success_outcomes`. Compliance gaps must be resolved before
      planning.

## Output

- Path to the new spec.
- Path to the stashed intake form (if `--file` given).
- Path to the researcher findings file (if `--brownfield` given).
- Path to `.soup/intake/active.yaml`.
- Integration count.
- Compliance flags echoed back.
- Routing hint: `/plan`, `/plan --architect-pre-pass`, or `/clarify`.

## Notes

- **`spec-writer` is the single source of truth for spec section
  names.** This command adds one new optional section
  (`## Integrations`, with per-integration subsection anchors) and
  the `spec-writer` agent card lists them as "populated by `/intake`
  when an intake form drives the spec".
- **No `stack_preference` / `deployment_target` in the spec.** Per
  Constitution Article I, specs describe *what*, not *how*. The
  `/plan` command reads the stashed `.intake.yaml` to seed the
  architect's tech-choice prompt without polluting the spec.
- **`compliance_flags` drives rule injection.** `/intake` writes
  `.soup/intake/active.yaml`; `subagent_start.py` reads it and
  appends matching `rules/compliance/<flag>.md` content to every
  subagent's `additionalContext`. See `rules/compliance/README.md`.
- **Validator-first.** A failed `IntakeForm.model_validate` aborts the
  command — the user must fix the form, not the spec.
- **Brownfield researcher is load-bearing, not optional cosmetic.**
  When `--brownfield` is used, the findings file is cited by
  `spec-writer` and consumed by `tasks-writer` via `context_excerpts`.
  Do not skip or truncate the findings write.
- **Rejection of free text.** If the user passes `/intake "build a
  dashboard"`, abort with a hint to either fill an intake form, use
  `--brownfield <path>`, or use `/specify "build a dashboard"`. The
  whole point of `/intake` is structure.
- **Existing-repo onboarding (ingestion, not extension).** Use
  [`/ingest-plans`](ingest-plans.md) when the task is salvaging
  prose `AGENT_*_SPEC.md` / `*_PLAN.md` / `*_HANDOFF.md` from a repo
  that already has plans to extract. `/intake --brownfield` is for
  the case where you are **building a new feature** against an
  existing repo whose contracts you need to respect.
