# Change budget

_How much change is "safe" in one PR. Complements CONSTITUTION.md
Article III (Implementation) — atomic commits are necessary but not
sufficient; the PR that collects them needs a size budget too._

## Iron law

```
Bigger diffs hide more bugs. Split before you hit 1000 LOC.
```

## Budget tiers

| Diff size | Files | Flow | Review depth |
|---|---|---|---|
| ≤ 20 LOC | 1-2 | `/quick` eligible — skip plan pipeline | One reviewer, skim pass |
| ≤ 200 LOC | 1-3 | Normal `/specify → /plan → /tasks → /implement` | Two reviewers, normal pass |
| 200 - 1000 LOC | 3-8 | Requires `architect` pre-pass; plan-writer must split TDD pairs | Two reviewers, incl. one specialist in the affected stack |
| > 1000 LOC | > 8 | Split into multiple ExecutionPlans — the plan-writer must emit ≥ 2 plans and a sequencing doc | Per-plan review |

LOC = **net** additions + deletions, excluding lockfiles and
generated code. A regenerated client (`contract-drift-detection`
phase 3) does not count against the budget because it's derivable
output, not human-authored code.

## `/quick` eligibility

`/quick` skips the full pipeline by design — it's for edits so
narrow that plan overhead would dominate. Eligibility:

- Diff ≤ 20 net LOC.
- No new files (rename counts as 0 LOC net).
- No `files_allowed` expansion required beyond one or two paths.
- No contract-drift risk — touches nothing under `contracts/`,
  `openapi/`, `*.proto`, `migrations/`, or shared zod schemas.
- No brownfield-baseline-capture needed — the fix is scoped tightly
  enough that neighbour breakage is implausible.

A fix that meets the LOC budget but crosses a contract boundary
never qualifies for `/quick`. Size is necessary, not sufficient.

## Architect pre-pass trigger (200-1000 LOC)

For diffs in the 200-1000 LOC range, the plan-writer must dispatch
`architect` for a pre-pass **before** emitting the ExecutionPlan.
The pre-pass outputs:

1. The natural split points within the goal (where a wave boundary
   should fall).
2. Any architectural ambiguity flagged for `/clarify`.
3. Risk rating (low / medium / high) with rationale.

This isn't review — this is planning input. The plan-writer consumes
the architect notes and may either write one plan or signal a split.

## > 1000 LOC — multi-plan rule

A single goal whose implementation exceeds 1000 LOC of hand-authored
change must split. Suggested split axes, in priority order:

1. **Expand / contract** — one plan for additive scaffolding, one
   for the switch-over, one for the contract cleanup. Mirrors the
   DB migration pattern in `rules/global/deprecation.md §Database`.
2. **Stack boundary** — one plan per stack (backend / frontend /
   infra). Each plan owns its verify pipeline.
3. **Surface vs. internals** — one plan that lands the public
   surface (routes, DTOs) with stubs; one plan that fills in the
   implementation.
4. **TDD RED waves** — if one plan would need > 3 RED steps, split
   so each plan has a coherent test frontier.

The plan-writer records the split axis in the plan goal's preamble.

## Breaking changes require a deprecation path

Any diff that removes or renames a public surface must route through
the deprecation cycle (see `rules/global/deprecation.md`). The
deprecation cycle is multi-PR by nature:

- PR 1 — add replacement, mark old as deprecated (soft-landing).
- PR 2..N — migrate callers, optionally with dashboards tracking
  call volume to the deprecated surface.
- PR M — remove the old surface.

Each PR in the cycle is independently sized to this rule. The full
deprecation cycle is rarely under the 200 LOC budget; splitting is
the default.

## Budget overrides

Exceeding the budget is not a hard block, but it requires:

1. Written rationale in the PR body (paragraph, not one line).
2. A specialist reviewer on the affected stack (not just
   `code-reviewer` + `security-scanner`).
3. Explicit sign-off from `architect` if the diff > 500 LOC without
   a pre-pass having been run.

The orchestrator never auto-rejects on size; the QA gate flags it
as `NEEDS_ATTENTION` with category=`style` and a `diff-size` tag.

## Cross-link

This rule is referenced from **CONSTITUTION.md Article III** as the
operational companion to atomic commits. Atomic commits govern the
shape of work *within* a plan; this rule governs the shape of the
plan itself.

See also:

- `rules/global/brownfield.md` — brownfield edits of any size need
  the baseline regardless of budget tier.
- `rules/global/deprecation.md` — breaking changes + size interact.
- `.claude/skills/brownfield-baseline-capture/SKILL.md` — the diff
  surfaces whether the budget fit the actual blast radius.
