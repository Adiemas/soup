# OpenHarness

A multi-agent harness with a strong emphasis on memory management
(session + long-term + consolidated), stack-aware agent rosters, and
hook-driven rule injection. Served as the pattern source for our
memory tiering and agent-roster topology. Relevance rating: strong.

- URL: https://github.com/openharness/openharness (representative)
- Research summary: synthesis across `research/01-adiemas.md` and
  `research/05-autoresearch.md`.

## What we took

- Four-tier memory model: `CLAUDE.md` (session steering),
  `MEMORY.md` (long-term facts), `.soup/memory/` (dream-consolidated
  summaries), `logging/agent-runs/*.jsonl` (trace).
- Stack-aware agent roster — specialists per language, not a single
  generic implementer.
- Hook-based rule injection at SubagentStart, so subagents inherit
  per-stack rules without the parent having to prompt them.
- "Agents exiting cleanly when their scope is satisfied" discipline
  — max_turns cap + explicit completion signal.
