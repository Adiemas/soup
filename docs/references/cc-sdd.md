# cc-sdd

A spec-driven-development implementation patterned on spec-kit but
tailored for Claude Code specifically — adds hook integration points
and a tighter `tasks` decomposition (TDD-shaped, one commit per task).

- URL: https://github.com/gotalab/cc-sdd
- Research summary: `research/08-sdd-testing.md`

## What we took

- TDD-shaped tasks: every `/tasks` output produces a pair of
  (failing test, implementation) steps with a hard ordering.
- One `TaskStep` = one atomic commit, Conventional Commits format.
  Enables bisect recovery if a later step regresses.
- `/implement` expectation that the orchestrator auto-runs
  `verify_cmd` between waves (we bolt this onto the DAG executor).
- The "no implementation without a failing test" phrasing used in
  the `tdd` skill.
