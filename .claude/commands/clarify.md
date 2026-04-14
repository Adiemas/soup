---
description: Resolve open questions in the latest spec via HITL prompts. Amends spec in place.
argument-hint: [spec-path]
---

# /clarify

## Purpose
Drive ambiguities in a spec to closure before planning. No guessing — every open question must get an explicit answer.

## Variables
- `$ARGUMENTS` — optional path to spec; defaults to most recent `specs/*.md`.

## Workflow
1. Locate target spec (most recent in `specs/` if not given).
2. Extract `## Open Questions` section.
3. For each question:
   a. Use AskUserQuestion with 2-4 crisp options.
   b. Allow "none of these — free text" as an escape hatch.
4. Amend the spec:
   - Move resolved questions into `## Requirements` (as new EARS statements) or `## Out of Scope`.
   - Keep unresolved ones in `## Open Questions`.
5. Append to the spec's final section: `## Clarifications` with date + answers.

## Output
- Questions resolved / remaining count.
- Diff summary.
- Next step: `/plan` once `## Open Questions` is empty or marked "deferred."

## Notes
- Never fabricate answers.
- If the user picks "free text" and it's underspecified, re-ask.
- Do not advance to `/plan` automatically — user must invoke.
