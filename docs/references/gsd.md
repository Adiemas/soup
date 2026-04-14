# gsd (Get Stuff Done)

A velocity-focused agentic harness that combines spec-driven flow
with a tight justfile for operator ergonomics. Emphasizes
"deterministic-where-possible" — every ergonomic flow has a scripted
fallback for CI. Relevance rating: strong for devx patterns.

- URL: https://github.com/kristapsk/gsd (representative — see research)
- Research summary: `research/07-gsd.md`

## What we took

- The justfile-first ergonomic layer. Our top-level `justfile`
  mirrors gsd's "verbs as recipes" structure.
- Deterministic fallback principle: every agentic recipe has a
  scripted equivalent (`just plan` runs meta-prompter without
  spawning subagents, for dry-run scripts).
- Per-feature worktree habit + atomic commit cadence.
- The emphasis on "don't ceremony the user" — short command surface,
  sensible defaults, HITL opt-in.
