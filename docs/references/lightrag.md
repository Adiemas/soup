# LightRAG (HKUDS)

A compact, production-oriented RAG pipeline combining dual-level
retrieval (local + global graph context) with graph-based knowledge
indexing. Runs on a standard Postgres + pgvector backend, has a first-
class Python API, and avoids the "framework-of-frameworks" sprawl of
LangChain. Relevance rating: 5/5.

- URL: https://github.com/HKUDS/LightRAG
- Research summary: `research/06-hkuds.md`

## What we took

- The full pipeline as our RAG substrate (`rag/`), not a custom
  implementation. We depend on `lightrag-hku>=1.0`.
- Postgres 16 + `pgvector` as the storage layer (see
  `docker/postgres-init.sql`).
- Dual-level retrieval: local (chunk-level similarity) and global
  (graph walk) — both surfaced in citation payloads.
- MCP server wrapper (`rag/mcp_server.py`) so the graph is queryable
  from any MCP-capable client, not just soup.
- Adapter pattern for ingestion sources (github / ado / fs / web) —
  LightRAG consumes normalized `Document` objects, we own the
  adapters.
- Chunk-boundary span tracking for citation (`[source:path#span]`)
  to satisfy Constitution VII.3.
