---
description: Author a user-facing spec (what + outcomes, not how). Produces specs/<slug>-<date>.md in EARS format. Supports --extends for spec extension.
argument-hint: "<goal description> [--extends <existing-spec-path>]"
---

# /specify

## Purpose
Create a fresh spec describing **what** to build and the **outcomes** users will experience. No tech choices. No "how." Outputs a spec document that downstream `/plan` reads as the authoritative intent.

> **For new apps, prefer [`/intake`](intake.md) with a YAML form over
> `/specify <goal>`.** The intake form removes a clarify round-trip,
> pre-populates the spec's `## Integrations` section, and threads each
> integration into downstream `TaskStep.context_excerpts` hints.
> `/specify` remains available for quick free-text iteration on
> existing apps, one-shot scratch specs, and spec **extensions** that
> augment an already-frozen parent.

## Variables
- `$ARGUMENTS` — free-text goal; required unless `--extends` also
  carries a narrowing description via `$ARGUMENTS` (in which case the
  extension scope is `<goal>`).
- `--extends <existing-spec-path>` — optional. When supplied, the new
  spec is authored as a **delta** against the parent spec at that
  path. The spec-writer inherits acceptance criteria, unresolved open
  questions, and frozen requirements (as an "existing contract"
  section) from the parent, then layers the extension. See §Extends
  mode below.

## Workflow
1. Parse flags. Extract `--extends <path>` if present. Reject
   `--extends` that point to a non-existent or unreadable path.
2. Invoke the `spec-writer` agent with `$ARGUMENTS` as the goal and
   (if `--extends` given) the path to the parent spec. The agent
   reads the parent spec in full before drafting.
3. The agent produces a spec using EARS requirement style ("The
   system shall <response> when <trigger>"). Section list is defined
   once in `.claude/agents/spec-writer.md` — the agent card is the
   single source of truth.
4. The 7 required sections (per `spec-writer.md`):
   - `## Summary`
   - `## Stakeholders & personas`
   - `## User outcomes`
   - `## Functional requirements`
   - `## Non-functional requirements`
   - `## Acceptance criteria`
   - `## Out of scope`

   Plus optional surfaces:
   - `## Open questions` — populated by `/clarify` if any remain; otherwise omit or write "none".
   - `## Integrations` — populated when an intake form lists
     integrations (normally from `/intake`; may appear in an
     `--extends` spec if the parent had one).
   - `## Extends` — required when `--extends` is set. See below.
5. Save to `specs/<slug>-<YYYY-MM-DD>.md`.
6. If `## Open questions` is non-empty (or unresolved), remind the
   user to run `/clarify` before `/plan`.

## Extends mode

When `--extends <parent-spec-path>` is set, `spec-writer` MUST:

1. **Read the parent spec in full** before drafting. Treat every
   parent requirement as frozen (Constitution I.4); the extension
   spec does not restate frozen requirements, it references them.
2. **Emit a `## Extends` section** near the top of the new spec with:
   - A link to `<parent-spec-path>` (relative path from the new
     spec's location).
   - A one-line statement of what this extension does to the parent
     (`"Adds <noun>"`, `"Augments <section>"`, `"Layers <capability>
     on top of <noun>"`).
   - A diff-style delta table:

     ```markdown
     | Parent REQ | Relation | Extension REQ | Note |
     |---|---|---|---|
     | REQ-3 | preserves | — | Byte-for-byte response shape retained. |
     | REQ-5 | augments | REQ-E-1 | Adds `distribution` key; existing fields unchanged. |
     | REQ-7 | deprecates | — | Marked deprecated; removal horizon: next minor. |
     | — | adds | REQ-E-2 | New capability; no parent counterpart. |
     ```

     Legal values for `Relation`:
     - `preserves` — no change; the parent REQ still governs.
     - `augments` — the extension tightens or supersets the parent
       REQ while preserving the parent's observable contract.
     - `deprecates` — the parent REQ is marked deprecated; the
       extension states the removal policy (see
       `rules/global/brownfield.md`).
     - `adds` — wholly new REQ with no parent counterpart.
3. **Inherit the parent's `## Acceptance criteria`** as an
   "Inherited acceptance criteria" subsection of the new spec's
   `## Acceptance criteria`. Every inherited criterion remains
   testable in the extension's scope.
4. **Inherit the parent's unresolved `## Open questions`** verbatim
   into the new spec's `## Open questions`. Parent questions do not
   auto-resolve by virtue of an extension.
5. **Reproduce the parent's frozen requirements** as a brief
   `## Existing contract` section — header plus the REQ IDs and
   one-line summaries (`REQ-3: The system shall return a 200 with
   JSON body ...`). The extension spec cites these; it does not
   restate the full parent.
6. **Never blindly copy the parent.** If the extension invalidates a
   parent REQ (e.g. a new auth model changes a permissive handler),
   flag the conflict: emit an `## Open questions` entry naming the
   parent REQ and the conflict. Do not silently replace it.

The `spec-writer` red-flags an extension that:
- Adds a REQ that contradicts a parent REQ without a
  `deprecates`/`augments` marker.
- Omits the `## Extends` section.
- Copies the full parent body verbatim instead of referencing it.

## Output
- Path to the new spec.
- Question count.
- If `--extends`: the `## Extends` delta summary (row counts by
  relation).
- Next step hint: `/clarify` or `/plan`.

## Notes
- Reject attempts to include tech stack, file paths, or implementation details — those belong in `/plan`.
- Specs are frozen once referenced by an ExecutionPlan. Use `/specify` again for a new version or `/specify --extends` for an extension.
- If `spec-writer.md` and this command ever disagree on section names, the **agent card wins**; update this file.
- **`/intake` cross-link.** When `/intake` invokes `spec-writer` in
  Mode B (structured intake form), the agent uses the same 7 required
  sections plus an additional `## Integrations` table. This command
  invokes `spec-writer` in Mode A (free-text goal) — the section list
  stays identical so downstream `/plan` reads either spec the same
  way. `--extends` is orthogonal to Mode A/B: you can extend a Mode A
  spec from a Mode B intake, or vice versa.
- **`--extends` and brownfield.** For an extension against an
  existing repository, consider
  [`/intake --brownfield <repo-path>`](intake.md) — it runs a
  researcher pre-pass to populate `context_excerpts` anchors before
  `spec-writer` drafts. Use `/specify --extends` when the parent spec
  already exists in `specs/` (under-soup work); use `/intake
  --brownfield` when you are extending a repository that never went
  through soup.
