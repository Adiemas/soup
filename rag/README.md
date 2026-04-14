# Soup RAG

LightRAG + Postgres + MCP wrapper. Enables `rag-researcher` and `/rag-*`
commands to pull cited context from Streck org knowledge.

## Quick start

### 1. Start Postgres with pgvector

```bash
docker run -d --name soup-rag-pg \
  -e POSTGRES_USER=soup -e POSTGRES_PASSWORD=soup \
  -e POSTGRES_DB=soup_rag \
  -p 5432:5432 pgvector/pgvector:pg16
```

Export the URL:

```bash
export POSTGRES_URL=postgres://soup:soup@localhost:5432/soup_rag
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...          # used only for embeddings
```

LightRAG will create its own schema on first run.

### 2. Ingest a source

```python
from rag import LightRagClient
from rag.ingest import Ingester

client = LightRagClient.from_env()
ingester = Ingester(client=client)

# Filesystem (default for bare paths)
await ingester.ingest_uri("file:///repo/docs")
# GitHub
await ingester.ingest_uri("github://streck/internal-docs@main")
# ADO Wiki
await ingester.ingest_uri("ado://streck/Platform")
# Public web docs
await ingester.ingest_uri("https://docs.example.com/api")
```

### 3. Query

```python
from rag.search import Searcher

searcher = Searcher(client=client)
print(await searcher.search_markdown("how do we deploy APIs?", mode="hybrid"))
```

### 4. Run the MCP server

```bash
python -m rag.mcp_server        # stdio transport by default
# or
soup rag-mcp                    # if the CLI is wired up
```

Register with Claude Code via `.claude/settings.json` (MCP servers list).

## Supported modes

| Soup mode | LightRAG mode | Use case |
|---|---|---|
| `hybrid` | `mix` | KG + vector blend (default) |
| `vector` | `naive` | Pure similarity search |
| `graph` | `global` | Knowledge-graph traversal |

## Citations

Every `Retrieval` carries `citation = "[source_path#span]"`. Downstream
agents MUST quote this tag per the fourth iron law (`CLAUDE.md`).

## Adding a new source adapter

1. Create `rag/sources/<name>.py` with a dataclass exposing:
   - `uri: str` property
   - `async def iter_chunks(self) -> AsyncIterator[Chunk]`
2. Export it from `rag/sources/__init__.py`.
3. Wire a URI scheme into `Ingester.build_source` in `rag/ingest.py`.
4. Add a test in `tests/test_rag.py` that exercises `iter_chunks`.

Chunks must preserve fenced code blocks — use `rag.ingest.chunk_text`
(it handles the boundary logic) rather than rolling your own splitter.

## Postgres unavailable?

`LightRagClient` initializes lazily and logs a warning when Postgres or
`lightrag-hku` is missing. All `search()` calls then raise
`rag.client.RagUnavailable`; tests skip gracefully.
