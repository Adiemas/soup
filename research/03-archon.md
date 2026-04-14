# Archon — Research Report

## Purpose
Workflow engine for AI coding agents that defines dev processes (planning, implementation, validation, code review, PR creation) as deterministic YAML workflows with per-node AI execution and task isolation via git worktrees. Remote agentic coding platform supporting Telegram/Discord/Slack/GitHub/web.

## Architecture

Monorepo (Bun + TypeScript):
- **@archon/core** — Orchestration, conversation state, command routing. Entry: `packages/core/src/handlers/command-handler.ts`. DB: SQLite/Postgres.
- **@archon/workflows** — DAG execution engine (`dag-executor.ts`): topological nodes, dependency resolution, AI prompting with output substitution, bash nodes, approval gates, retry.
- **@archon/providers** — Pluggable AI via `IAgentProvider` (`packages/providers/src/types.ts`): `sendQuery()` generator, capability flags, model validation. Built-in: Claude (MCP-aware), Codex.
- **@archon/adapters** — Platform adapters (Telegram/Discord/Slack/GitHub/Gitea/GitLab).
- **@archon/server** — Hono web server with SSE, webhooks.
- **@archon/web** — React+Vite UI (chat, workflow viewer, DAG graph).

## Patterns Worth Stealing

1. **MCP Node-Level Config** — `packages/providers/src/claude/provider.ts::loadMcpConfig()`. Per-node `.mcp.json` in YAML workflows via `nodeConfig.mcp`. Env-var expansion via `expandEnvVars()`. Auto-wildcard tool allowlist `mcp__${serverName}__*` injected into `options.allowedTools`.

2. **Provider Interface** — `packages/providers/src/types.ts`. Contract: `IAgentProvider { sendQuery(): AsyncGenerator<MessageChunk>, getCapabilities(): ProviderCapabilities }`. MessageChunk discriminated union. Capability flags (mcp, hooks, skills, structuredOutput, effortControl). Dag-executor warns on unsupported features.

3. **Context Engineering (Orchestrator Prompt Builder)** — `packages/core/src/orchestrator/prompt-builder.ts::buildOrchestratorPrompt()` composes: registered project list, available workflows, routing rules. Project-scoped variant pins active project. Workflow invocation: `/invoke-workflow {name} --project {name} --prompt "{desc}"`.

4. **Task/Workflow Persistence** — `packages/core/src/db/workflows.ts`. Schema: `WorkflowRun { id, workflow_name, conversation_id, status, metadata (github_context), working_path, timestamps }`. Terminal states in `TERMINAL_WORKFLOW_STATUSES`. Orphaned runs marked failed on startup. Metadata validation fails loudly.

5. **Git Worktree Isolation** — per-conversation branch in isolated checkout. Excellent for parallel task execution.

## What to Adapt vs Adopt

**Borrow (don't embed):**
- `loadMcpConfig()` + `expandEnvVars()` (20 LOC)
- `IAgentProvider` + `MessageChunk` (50 LOC)
- `buildOrchestratorPrompt()` + project-scoped variant (150 LOC)
- `WorkflowRun` schema + persistence helpers (100 LOC)
- `classifyError()` from `utils/error-classifier.ts` (50 LOC)

**Don't embed wholesale:**
- Full stack (Bun + SQLite/Postgres + Hono + React). Too heavy.
- Workflow YAML loader (~400 LOC schema parsing).
- Multi-platform adapters.

## Gaps
1. No RAG pipeline (workflow-centric, not knowledge-centric). Relevance 3/5.
2. No doc ingestion (GitHub/ADO wikis/library docs). Relevance 2/5.
3. Tight Claude SDK coupling. Relevance 3/5.
4. Workflow YAML DSL is heavy. Relevance 4/5.
5. Multi-platform complexity overkill. Relevance 1/5.
6. Git worktree isolation — adopt. Relevance 4/5.
7. Task tracking across sessions — critical. Relevance 5/5.

## Relevance: 4/5

## Recommendation
Build soup as **lightweight knowledge + task backbone**. Steal: MCP pattern, provider interface, prompt builder, workflow persistence, worktree isolation. Skip: multi-platform, heavy YAML DSL, embedded CLI. Focus on:
- Agentic RAG (over Archon's static context)
- Doc ingestion (GitHub/ADO/library docs)
- Context engineering (vector + metadata)
- Task graph with knowledge linkage
