# Archon

An orchestration framework that executes Pydantic-validated
`ExecutionPlan` DAGs against isolated git worktrees, with per-wave
parallelism and verification gates between waves. Archon's
orchestrator is the direct progenitor of `orchestrator/` in soup.
Relevance rating: 5/5.

- URL: https://github.com/coleam00/Archon (canonical reference)
- Research summary: `research/03-archon.md`

## What we took

- The `ExecutionPlan` / `TaskStep` schema shape (topological layers,
  `depends_on`, `parallel`, `verify_cmd`, `files_allowed`,
  `max_turns`).
- Wave-based execution model: compute ready set, spawn in parallel,
  barrier on wave completion, then advance.
- Per-feature worktree isolation; no direct edits to main branch.
- Fresh subagent per step — no context bleed between tasks.
- Auto-dispatched `verifier` (fix-cycle role) on `verify_cmd` failure,
  with failure context + spec excerpt passed in.
- Explicit rejection of Archon's multi-platform adapters
  (Slack / Telegram / Discord) — overkill for internal dev, see
  `DESIGN.md §10`.
