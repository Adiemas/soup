# nanobot

A memory-first small-agent framework exploring dream-consolidation —
post-session summarization of long transcripts into paragraph-sized
durable notes. Relevance rating: medium; we adopted the idea,
deferred the full implementation.

- URL: https://github.com/nanobot/nanobot (representative)
- Research summary: synthesis across memory discussions in
  `research/01-adiemas.md` and `research/05-autoresearch.md`.

## What we took

- The **dream-consolidation** concept: on worktree merge (APPROVE),
  the Stop hook triggers a summarizer that distills the session's
  essential decisions into `.soup/memory/<slug>.md` — ~2 KB per
  feature, injected into future SubagentStart contexts.
- The principle that long session traces should not grow the
  steering context directly; they compress first, then surface.
- Size caps on memory artifacts (steering under 500 lines; dream
  summaries under ~2 KB) to keep context spend bounded.

Explicitly NOT copied: nanobot's full dream-consolidation worker
(`DESIGN.md §10`) — deferred until memory volume demands it; current
summarizer is a simple sonnet one-shot, not a background worker.
