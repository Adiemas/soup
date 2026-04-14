---
description: Architect + plan-writer produce .soup/plans/<slug>.md with tech choices, referencing the latest clarified spec. Markdown-only; /tasks converts to JSON.
argument-hint: [spec-path]
---

# /plan

## Purpose
Translate an approved spec into architecture + tech + task skeleton. Output is a **markdown** document; the JSON ExecutionPlan is authored separately by `/tasks` (which invokes `tasks-writer`).

## Variables
- `$ARGUMENTS` — optional spec path; defaults to most recent `specs/*.md` with no open questions. If multiple candidates tie, abort and AskUserQuestion.

## Workflow
1. Resolve spec path. Reject if `## Open questions` is non-empty (tell user to `/clarify`).
2. **Resolve stashed intake YAML (if present).** Look for a sibling
   file next to the spec: `specs/<slug>-<date>.intake.yaml`. If it
   exists, parse it with `schemas.intake_form.IntakeForm.from_yaml`
   and extract these fields for structured hand-off to the architect:
   - `stack_preference`
   - `deployment_target`
   - `compliance_flags[]`
   - `integrations[]` (full list with `kind`, `ref`, `purpose`, `auth`)
   If the YAML parse fails, abort with a clear error — an invalid
   intake YAML next to a frozen spec is a corruption, not a soft
   fallback situation. If the YAML is simply absent (e.g. the spec
   came from free-text `/specify`), continue without those fields;
   the architect derives tech choices from spec prose in that case.
3. Invoke `architect` (opus) with the spec contents, `CONSTITUTION.md`,
   and the **structured intake block** (when present). The architect
   prompt separates:
   - **Narrative inputs** — the spec prose (drives design rationale).
   - **Structured inputs** — the intake YAML fields listed above
     (drive tech choices). Pass these as a labelled block; the
     architect treats these as ground truth and does NOT re-derive
     stack or compliance obligations from prose.

   Architect output:
   - Emits architecture: components, data flow, dependencies, risks.
   - Chooses tech per Streck stack (Python/.NET/React/TS/Postgres/Docker).
     When the intake YAML supplies a `stack_preference`, the architect
     honours it unless there is a clear rationale to override (if
     overriding, the architect must name the rationale in the design
     doc's Options Considered section).
   - Notes every `compliance_flag` and the downstream obligations
     it implies (see `rules/compliance/README.md`).
4. Invoke `plan-writer` (sonnet) with architect output + spec:
   - Produces `.soup/plans/<slug>.md` — MARKDOWN ONLY. Section list is defined once in `.claude/agents/plan-writer.md`; that card is the source of truth.
   - Required sections: `## Spec`, `## Constitution ref`, `## Overview`, `## Architecture`, `## Tech choices`, `## File map`, `## Risks & mitigations`, `## Task outline`, `## Budget`.
5. Present summary to user; suggest `/tasks` to formalize the markdown into validated JSON.

## Output
- Plan path (`.soup/plans/<slug>.md`).
- Architecture summary (<=10 bullets).
- Tech choices table.
- Intake YAML path (if consumed), integration count, compliance flags echoed.
- Next step: `/tasks`.

## Notes
- Plans are invalidated if the spec changes or the constitution bumps.
- Architect output must not include code; only decisions.
- If plan-writer's section list and this command disagree, the **agent card wins**; update this file.
- **Intake YAML is the source of truth for stack, deployment, and
  compliance.** Spec prose is for narrative — when the intake YAML is
  present, fields like `stack_preference`, `deployment_target`, and
  `compliance_flags[]` flow from YAML into the architect prompt
  directly. This removes the "architect re-derives the stack from
  prose" brittleness documented in the iter-2 intake-form report. If
  a field is in both the intake and the spec prose and they disagree,
  **the intake wins** — the spec prose is narrative framing, not
  ground truth for routing fields.
- **File map feeds `context_excerpts` hints downstream.** `/tasks` converts this markdown into JSON; it reads the `## File map` section to decide which `TaskStep.context_excerpts` / `spec_refs` entries to set on each step. When writing the file map, annotate each path with the spec section it implements so the downstream `tasks-writer` can emit `context_excerpts: ["specs/<name>.md#<anchor>"]` without guessing. Example: `src/api/auth.py -- implements specs/auth.md#token-rotation`. `plan-writer` need not emit the JSON fields itself; the annotated markdown is enough.
- **Per-integration anchors.** When the spec was emitted by `/intake`
  (Mode B) with a populated `## Integrations` section, it carries one
  `### <kind>: <ref>` subsection per integration (anchored e.g.
  `#integration-asset-tracker-rest`). `plan-writer` should annotate
  each adapter file in `## File map` with the *per-integration*
  anchor so `tasks-writer` can emit finer-grained
  `context_excerpts` — one integration's slice of the spec per step,
  not the whole table. Example: `app/services/asset_tracker.py --
  implements specs/pipette-dashboard.md#integration-asset-tracker-rest`.
