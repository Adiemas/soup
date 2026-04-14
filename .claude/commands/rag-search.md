---
description: Query org knowledge (LightRAG-backed). Returns cited results [source:path#span].
argument-hint: "<query>"
---

# /rag-search

## Purpose
Retrieve relevant knowledge from the org index (GitHub repos, ADO wikis, filesystem, web docs) with inline citations.

## Variables
- `$ARGUMENTS` — free-text query; required.

## Workflow
1. Invoke `rag-researcher` agent with the query.
2. Agent calls `rag/search.py::Searcher.search(query, mode="hybrid", top_k=8)`.
3. Agent filters, re-ranks if needed, and emits markdown:
   - Top-N results, each as a blockquote with `[source:path#span]` citation.
   - Short synthesis paragraph citing multiple sources.
4. If the query indicates an ongoing research task (hints: "compare", "explain all", "find every"), agent enters autoresearch loop (see `agentic-rag-research` skill): iterative narrow-down, max 5 iterations, bounded budget.

## Output
- Synthesis paragraph + cited excerpts.
- Result count + coverage summary (which sources hit).
- Suggested follow-up queries.

## Notes
- Every claim must be cited. Uncited sentences are flagged.
- If LightRAG/Postgres is down, command degrades to filesystem-only search with warning banner.
