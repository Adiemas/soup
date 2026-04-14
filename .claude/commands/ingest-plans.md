---
description: Brownfield onboarding — convert prose agent/plan/handoff files into ExecutionPlan JSON skeletons. Never skips manual review.
argument-hint: [glob]
---

# /ingest-plans

## Purpose
Onboard a brownfield repo that already runs a document-driven multi-agent
pipeline (e.g. `AGENT_*_SPEC.md`, `*_PLAN.md`, `*_HANDOFF.md`) onto Soup
by extracting the work items the prose already describes into skeleton
`ExecutionPlan` JSON files for human review.

This command is the lever behind `just ingest-plans <glob>`. It exists
because rewriting prose plans into Soup's validated DAG by hand is the
single biggest onboarding tax for existing repos (see the
warhammer-40k-calculator dogfood note in
`docs/real-world-dogfood/warhammer-40k-calculator.md`).

## Variables
- `$ARGUMENTS` — a shell glob relative to the project root
  (e.g. `"AGENT_*_SPEC.md"`, `"plan/*_PLAN.md"`,
  `"*_HANDOFF.md"`).

## When to invoke
- You just ran `/soup-init` in a repo that already has prose multi-agent
  docs and you want the skeleton plans generated before you start
  consolidating.
- An engineer hands you a pile of `AGENT_*.md` files and asks "can you
  turn these into Soup plans?"
- You are auditing a repo's implicit DAG and want a structured read of
  its phases without rewriting them.

## Do NOT invoke when
- The repo has no pre-existing prose plan docs — just use `/specify +
  /plan + /tasks` to create a first-class Soup plan.
- The output will be executed directly without human review. The
  skeletons contain `TODO:` markers and default `verify_cmd: "true"`;
  running them as-is is strictly worse than a hand-written plan.

## Workflow
1. Run `just ingest-plans "<glob>"`.
2. The meta-prompter runs in **INGEST mode** (not its normal planning
   mode). It reads each matched prose file and emits a skeleton
   `ExecutionPlan` JSON under `.soup/ingested/<source-slug>.plan.json`.
3. A summary table prints per-file: input path, steps extracted, and a
   note listing unresolved fields (`N step(s) with TODO`,
   `M with empty files_allowed`, etc.).
4. **Manual review gate (non-optional).** Open each generated JSON:
   - Replace every `TODO: define verify_cmd` with a real command.
   - Replace every `TODO: scope files_allowed` with globs.
   - Replace every `TODO: pick specialist agent` with the right roster
     entry.
   - Replace every `TODO: clarify` with concrete requirements, or
     delete the step if the prose was too vague.
5. Validate the cleaned-up skeleton with `soup plan-validate <path>`.
6. Move (or copy) the validated file into `.soup/plans/<slug>.json` to
   hand off to `/implement`.

## Output
- One `.soup/ingested/<source-slug>.plan.json` per matched prose file.
- A summary table printed to stdout.
- Exit code 0 unless `--fail-fast` was passed and at least one file
  failed meta-prompter extraction.

## Notes
- Ingest mode uses a different system prompt from `plan_for(goal)` — it
  is explicitly anti-hallucination (prose is silent → `TODO:`; fields
  cannot be inferred → use defaults + mark gap in step prompt).
- Skeletons are emitted under `.soup/ingested/`, not `.soup/plans/`, so
  the unreviewed output cannot be picked up by `soup go` or
  `/implement` accidentally.
- One prose work-item maps to one `TaskStep`. Sub-bullets inside a
  phase are compressed into the step's `prompt`, not exploded into
  separate steps — keeping the generated DAG scannable.
- `context_excerpts` and `spec_refs` are left empty by default. After
  review, you should set `spec_refs` to the source prose file (or its
  distilled spec) so subagent runs see the domain knowledge in-band.
- The generated `goal` reflects the source filename, not a user intent;
  rewrite it before execution.
