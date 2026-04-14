---
description: View or amend CONSTITUTION.md (hard project rules). Interactive, HITL-gated.
argument-hint: [view|edit|bump]
---

# /constitution

## Purpose
Inspect or amend the project Constitution — the single source of hard rules all agents obey. Every amendment invalidates in-flight plans.

## Variables
- `$ARGUMENTS` — optional verb: `view` (default), `edit`, `bump`

## Workflow
1. Read `CONSTITUTION.md` and present its current version + article headings.
2. If `view` (default): display and stop.
3. If `edit`:
   a. Use AskUserQuestion to get the intent (which Article, what change, rationale).
   b. Propose a diff.
   c. AskUserQuestion to confirm.
   d. Apply edit via Edit tool.
   e. Increment the version string in the Constitution header.
   f. Append an entry to `MEMORY.md` under `## Decisions`: `<date> — Constitution v<new> — <rationale>`.
   g. List all `.soup/plans/*.json` marked not-yet-run and tag them `constitution_stale=true`.
4. If `bump`: no content change; bump version only (for rebroadcast after unrelated churn).

## Output
- Echo the new version.
- Summary of what changed.
- List of plans now marked stale.

## Notes
- Never auto-apply edits; always require AskUserQuestion confirmation.
- Do NOT commit changes from within this command; leave staged for user to review.
