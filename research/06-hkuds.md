# HKUDS Cluster — Research Report

## 1. LightRAG — Production RAG (Graph + Vector Hybrid)

**Purpose:** Enterprise RAG combining knowledge graphs with semantic search. EMNLP2025.

**Key Abstractions:**
- **Indexing:** LLM-powered entity-relationship extraction → graph construction
- **Dual-Level Retrieval:** Vector (BAAI/bge-m3, OpenAI) + Graph traversal (Neo4j, Postgres)
- **Storage:** Pluggable backends (Postgres, MongoDB, Neo4j, OpenSearch); document deletion + auto graph regen
- **Chunking:** Context-aware segmentation preserving entity boundaries (512-2048 tokens)
- **Reranking:** Post-retrieval refinement

**Patterns Worth Stealing:**
- Incremental ingestion (add doc → extract entities → upsert → rebuild indices)
- Citation tracking (trace RAG answer back to source — critical for org wikis)
- Multimodal via RAG-Anything (images, video, PDFs)
- Graph visualization WebUI

**Integration:**
- **Primary:** Python library (`lightrag-hku` PyPI) with Postgres backend. Subagent watches ADO wiki/GitHub for commits, extracts, upserts.
- **Secondary:** MCP server wrapper (`rag:search`, `rag:add_documents`).

**Relevance: 5/5** — Direct fit for org knowledge indexing.

## 2. OpenHarness — Agent Harness Framework

**Purpose:** Lightweight infrastructure for multi-agent orchestration with permissions, memory, tool coordination.

**Key Abstractions:**
- **Agent Loop:** `query → stream → tool-call → loop` with streaming + API retries
- **Tool Registry:** Pydantic-based 43+ tools with auto JSON schema, permission checks, lifecycle hooks
- **Coordinator:** Subagent spawning, team registry, background task lifecycle
- **Permission Model:** Multi-level (path rules, command restrictions, provider access)
- **Memory:** `CLAUDE.md` (session) + `MEMORY.md` (long-term)
- **Skills:** On-demand markdown knowledge loading

**Patterns Worth Stealing:**
- Hierarchical teams → maps to Streck orchestrator/team-lead/worker
- Hook system (pre/post tool) for logging, sandboxing, approval
- Provider abstraction (Claude/OpenAI/Copilot swap via config)
- Tool composability (tools can spawn subagents → recursive decomposition)

**Integration:**
- **Primary:** Conceptual template for Coordinator + permission model
- **Secondary:** Base class inheritance pattern (don't embed library)

**Relevance: 4/5**

## 3. CLI-Anything — LLM-Powered CLI Wrapper Generator

**Purpose:** Transforms application source into agent-callable CLIs with structured output.

**Key Abstractions:**
- **7-Phase Pipeline:** Analyze → Design → Implement (Click) → Test Plan → Test Write → Document → Publish
- **Dual Modes:** REPL + Subcommand; both `--json` for agents
- **Authentic Integration:** No mocks; delegates to real backends

**Patterns Worth Stealing:**
- Auto-generated `--json` wrappers for ADO CLI, psql, Docker, dotnet
- JSON-output-by-default (agents consume structured data, not scraped text)
- Systematic testing (2,130+ tests)
- Auto-generated SKILL.md for agent introspection

**Integration:**
- **Primary:** Subagent tool wrappers (ADO, psql, docker, dotnet) returning `--json`
- **Secondary:** Click + pydantic patterns for custom Streck CLIs

**Concrete Use:** `adocli:list_work_items(project, query)`, `db:query(sql)`, `docker:run_container(image, args)` — all JSON to orchestrator.

**Relevance: 4/5**

## 4. Nanobot — Minimalist Agent Framework

**Purpose:** Ultra-lightweight personal AI agent (99% fewer LOC than alternatives).

**Key Abstractions:**
- Agent loop (`agent/loop.py`)
- Context builder (`agent/context.py`) — assembles prompts from history + state
- Memory: append-only history + Dream consolidation (summarizes → MEMORY.md)
- Provider registry (Claude/OpenRouter/DeepSeek/Ollama swap)
- Channel abstraction (Telegram/Discord/Feishu/Slack/Email via message bus)
- Tool sandboxing (`restrictToWorkspace`, `bwrap`)

**Patterns Worth Stealing:**
- Minimalism principle
- Session isolation (`channel:chat_id` independent state)
- Graceful degradation
- Memory consolidation (Dream promotes workflows to skills)

**Integration:**
- **Primary:** Reference implementation (don't embed)
- **Secondary:** Lightweight subagent base for simple workers

**Relevance: 2.5/5**

## Synthesis

**Embed as Dependencies:**
- **LightRAG** (`lightrag-hku` PyPI) — RAG pipeline, MCP wrapper.

**Adapt (no direct dependency):**
- **OpenHarness** — Coordinator abstraction, permissions, team spawning.
- **CLI-Anything** — 7-phase pattern + dual-mode for ADO/psql/Docker wrappers.
- **Nanobot** — Simplicity + session isolation + memory consolidation as organizational reference.

**Soup Architecture:**
- **Orchestrator** (OpenHarness + nanobot inspired): spawns team, tracks state in MEMORY.md
- **RAG Subagent** (LightRAG embedded): ingests org docs, exposes `search()` via MCP
- **Tool Wrappers** (CLI-Anything): ADO/psql/docker/dotnet `--json` subagents
- **Worker Agents** (nanobot): minimal loops, session isolation
