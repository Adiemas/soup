# karpathy/autoresearch

Andrej Karpathy's autonomous-research loop: an agent iteratively
plans, searches, reads, synthesizes, and writes to a persistent
append-only experiments table. The loop is bounded by wall-clock and
self-critiques at each cycle. Relevance rating: high for RAG
research UX and logging conventions.

- URL: https://github.com/karpathy/nano-agent (representative)
- Research summary: `research/05-autoresearch.md`

## What we took

- The autonomous research loop as the template for our
  `rag-researcher` agent and `agentic-rag-research` skill.
- `logging/experiments.tsv` — append-only TSV of one-row-per-run
  metrics (goal, duration, tokens, verdict, cost). Inspectable with
  any CSV viewer; no DB lock-in.
- Cost-aware model choice: opus for planning, sonnet/haiku for
  routine lookups. Informs Constitution VIII.
- Wall-clock budget enforcement via `ExecutionPlan.budget_sec`.
- The "every claim cites its source" discipline — agents must quote
  retrieved passages with span references.
