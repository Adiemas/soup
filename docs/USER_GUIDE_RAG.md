# Soup RAG — User Guide

_Practical, copy-pasteable walkthrough for Streck engineers who need to
pull GitHub repos and ADO wikis into Soup's RAG index, then query them
from `/rag-search`, the `rag-researcher` subagent, or any MCP client._

> Audience: a Streck engineer on a fresh Windows laptop with `soup`
> cloned to `C:\dev\soup`, an `ADO_PAT`, and a `GITHUB_TOKEN`.
> Goal: be able to ingest a repo + wiki and run a cited query inside
> 15 minutes.

---

## 0. TL;DR

```bash
# one-time
docker compose -f docker/docker-compose.yml up -d postgres
cp .env.example .env                # then fill ANTHROPIC_API_KEY,
                                    # OPENAI_API_KEY, GITHUB_TOKEN, ADO_PAT
just init                           # venv + hooks + postgres

# ingest
python -m rag.ingest --source github://streck/auth-service@main
python -m rag.ingest --source ado://streck/Security/Security.wiki

# query
python -m rag.search --query "how does AuthService validate JWTs?"

# expose to Claude Code via MCP
just rag-mcp                        # stdio server on this terminal
```

---

## 1. Prerequisites

| Component | Why | Install |
|---|---|---|
| Python 3.12 | Soup runtime | `winget install Python.Python.3.12` |
| `uv` | venv + dependency installer (recommended) | `winget install astral-sh.uv` |
| Docker Desktop | Postgres + pgvector container | `winget install Docker.DockerDesktop` |
| `just` | three-mode developer CLI | `winget install Casey.Just` |
| `gh` (optional) | GitHub PR/issue ops by `github-agent` | `winget install GitHub.cli` |
| Azure CLI + devops ext (optional) | ADO ops by `ado-agent` | `winget install Microsoft.AzureCLI` then `az extension add --name azure-devops` |

### 1.1 Required environment variables

Edit `.env` after `cp .env.example .env`:

```bash
# ── Required for any RAG run ─────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...        # meta-prompter + every subagent
OPENAI_API_KEY=sk-...               # LightRAG embedding func (1536-dim)

# ── Required for Postgres-backed RAG (recommended) ───────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=soup_rag
POSTGRES_USER=soup
POSTGRES_PASSWORD=soup
# rag/client.py also reads POSTGRES_URL / DATABASE_URL if present:
POSTGRES_URL=postgres://soup:soup@localhost:5432/soup_rag

# ── Required for GitHub source ───────────────────────────────
GITHUB_TOKEN=ghp_...                # PAT or fine-grained token
GITHUB_ORG=streck                   # default repo namespace

# ── Required for ADO wiki source ─────────────────────────────
ADO_ORG=streck                      # https://dev.azure.com/streck
ADO_PROJECT=Platform                # default project for ado-agent
ADO_PAT=...                         # PAT with Read on Wiki + Work Items
```

> **PAT scopes.** `ADO_PAT` minimum: _Wiki (Read), Work Items (Read)_.
> If you also use `ado-agent` for write ops, add _Code (Read & write)_,
> _Pipelines (Read & execute)_, _Work Items (Read & write)_.
>
> **GITHUB_TOKEN.** For private repo ingestion, the token must have
> `repo` scope (classic PAT) or fine-grained `Contents: Read`. Public
> repos work without a token but you'll hit the 60 req/h anonymous
> rate limit and ingestion of any repo with >60 blobs will fail
> partway.

### 1.2 Postgres + pgvector

```bash
# either via docker compose (recommended)
docker compose -f docker/docker-compose.yml up -d postgres

# or standalone
docker run -d --name soup-rag-pg \
  -e POSTGRES_USER=soup -e POSTGRES_PASSWORD=soup \
  -e POSTGRES_DB=soup_rag \
  -p 5432:5432 pgvector/pgvector:pg16

# verify
psql postgres://soup:soup@localhost:5432/soup_rag -c '\dx'
# look for: vector | 0.x.x | public | vector data type and ivfflat ...
```

LightRAG creates its own `kv_*`, `vector_*`, `doc_status_*`, and
`graph_*` tables on first ingestion — no manual schema work.

### 1.3 Sanity check

```bash
just doctor               # framework-wide preflight
python -c "from rag.client import LightRagClient; \
           c = LightRagClient.from_env(); print(c.postgres_url)"
```

If `postgres_url` prints `None`, you forgot to source `.env` (the
`session_start` hook does this for Claude Code sessions, but a bare
`python -c` from cmd.exe does not — open a Git Bash shell with
`set -a; source .env; set +a` first, or use `just rag …` recipes
which load `.env` automatically).

---

## 2. Ingest a GitHub repo

### 2.1 Command

```bash
# whole repo, default branch
python -m rag.ingest --source github://streck/auth-service

# specific branch
python -m rag.ingest --source github://streck/auth-service@release/2026.04

# dry-run (count chunks, don't write)
python -m rag.ingest --source github://streck/auth-service --dry-run

# tag the source (metadata flows into Chunk.metadata)
python -m rag.ingest --source github://streck/auth-service --tags backend,auth
```

### 2.2 Expected stdout

```json
{
  "status": "ok",
  "mode": "ingest",
  "report": {
    "source_uri": "github://streck/auth-service@main",
    "chunks_seen": 412,
    "chunks_inserted": 412,
    "chunks_skipped_duplicate": 0,
    "errors": []
  }
}
```

A re-run on an unchanged repo emits `chunks_skipped_duplicate == chunks_seen`
because `Chunk.hash()` (sha1 over `source_path + span + content`) is
checked client-side. LightRAG also dedups on its own document content
hash, so duplicates are cheap.

### 2.3 What gets ingested

`GithubRepoSource.iter_chunks` walks
`GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1` and yields
chunks for every blob whose extension is in the allow-list:

```
.md .markdown .rst .txt .py .cs .csproj .ts .tsx .js .jsx
.sql .yaml .yml .toml .ini .json .sh .bash .go .java .kt
.rb .rs .scala .swift .proto .graphql
```

Files >1.5 MB are skipped. There is no `.gitignore` respect today
(see TODO in `rag/sources/github.py`); a checked-in `node_modules/`
or `.env` would NOT be ingested only because `.env` is not in the
extension list. **Do not check in secrets and rely on the extension
list to save you.**

### 2.4 Caveats

- **Issues + PRs are not ingested.** Only the merged tree.
- **Truncated trees.** `GET /git/trees?recursive=1` caps at ~100k
  entries. Very large monorepos get a `truncated: true` warning and
  silently lose tail entries.
- **Anonymous rate limit (60 req/h).** Without `GITHUB_TOKEN`,
  anything past a tiny repo will partially ingest and log a flurry
  of `blob fetch failed: 403` warnings.
- **No incremental updates** between runs. Re-ingest re-fetches every
  blob; dedup is in-memory only. For a 1k-file repo at ~5 KB average
  blob, that's ~5 MB per re-ingest.

---

## 3. Ingest an ADO wiki

### 3.1 Command

```bash
# discover wiki ID automatically (picks values[0] from the wiki list)
python -m rag.ingest --source ado://streck/Security

# pin a wiki by id or name
python -m rag.ingest --source ado://streck/Security/Security.wiki

# dry-run
python -m rag.ingest --source ado://streck/Security --dry-run
```

### 3.2 Expected stdout

```json
{
  "status": "ok",
  "mode": "ingest",
  "report": {
    "source_uri": "ado://streck/Security/Security.wiki",
    "chunks_seen": 78,
    "chunks_inserted": 78,
    "chunks_skipped_duplicate": 0,
    "errors": []
  }
}
```

### 3.3 What gets ingested

`AdoWikiSource.iter_chunks`:

1. Resolves the wiki ID via
   `GET /{org}/{project}/_apis/wiki/wikis?api-version=7.1` if not
   provided. **Today this picks `values[0]` blindly** — fine for
   single-wiki projects, fragile for multi-wiki ones (TODO logged).
2. Lists pages with `recursionLevel=full`.
3. Walks the tree, fetches each page with `includeContent=true`, and
   renders the page markdown into chunks via the same `chunk_text`
   pipeline as filesystem sources.

`source_path` becomes `ado://streck/Security/<wikiId>/<page-path>.md`,
which preserves the page hierarchy so citations point straight to the
wiki page.

### 3.4 Caveats (read these before reporting bugs)

- **Code wikis vs project wikis** are not distinguished. A code wiki
  needs a `versionDescriptor` (branch/commit) on every page request;
  the current implementation omits it and will 404 on code wikis with
  a non-default branch. Workaround: ingest only project wikis until
  iter-3 ships the fix.
- **Attachments are dropped.** PNG/PDF embeds in pages become broken
  markdown links in retrieved chunks. The visual context is lost.
- **No incremental updates.** Each re-ingest re-fetches every page and
  re-streams its content; LightRAG and the in-memory hash set dedup,
  but the API round-trip cost is paid every time.
- **Pagination missing.** Wikis with >5k pages can time out on the
  initial `?recursionLevel=full` call. Smaller wikis (<1k pages) run
  comfortably under 90 s on a typical broadband link.
- **403 / 401 with PAT set.** Most common cause is PAT scope —
  re-issue with at least _Wiki (Read)_ and check the `org` value
  matches your dev.azure.com URL.

---

## 3b. Ingest ADO work items (`ado-wi://`)

Iter-3 ships `AdoWorkItemsSource` so `STRECK-482` references in a
spec can be auto-pulled into the RAG index without hand-copying the
work-item body.

### 3b.1 Command

```bash
# single work item by numeric ID
python -m rag.ingest --source "ado-wi://streck/Platform/482"

# all Active items assigned to you (filter clause — adapter wraps as WIQL)
python -m rag.ingest --source "ado-wi://streck/Platform/[System.AssignedTo] = @Me AND [System.State] = 'Active'"

# full WIQL pastes untouched
python -m rag.ingest --source "ado-wi://streck/Platform/SELECT [System.Id] FROM WorkItems WHERE [System.Tags] CONTAINS 'auth'"
```

### 3b.2 What gets ingested

For each resolved work-item ID the adapter materialises:

```markdown
# <Type> <id>: <title>

- **State:** <state>
- **Type:** <type>
- **Assigned to:** <displayName>

## Description
<System.Description, rendered markdown>

## Acceptance criteria
<Microsoft.VSTS.Common.AcceptanceCriteria>

## Comments
### <author> — <timestamp>
<comment body>
```

`source_path` is `ado-wi://<org>/<project>/<query>#wi-<id>`, so
citations land as e.g.
`[source:ado-wi://streck/Platform/482#wi-482#acceptance-criteria]`
once the chunker's markdown-anchor fallthrough runs.

### 3b.3 Stub-safe behaviour

With no `ADO_PAT`, the adapter logs a warning and returns zero
chunks. Matches the `.env.example` stub-safe contract — no crash,
no half-formed writes.

### 3b.4 Flow with `spec-writer` / `architect`

When a spec or plan contains `STRECK-<n>` or `ADO-<n>` references and
`ADO_PAT`, `ADO_ORG`, and `ADO_PROJECT` are set, soup will surface
the refs to `ado-agent` which (iter-3) auto-fetches the work items
via `AdoWorkItemsSource` and threads
`ado-wi://<org>/<project>/<id>` into `spec_refs` for downstream
resolution. If the env is unconfigured, soup logs a friendly hint
and leaves the ref in `spec_refs` unresolved — future `ado-agent`
runs materialise it when the env catches up.

---

## 4. Query the index

### 4.1 CLI

```bash
python -m rag.search --query "how does AuthService validate JWTs?"
python -m rag.search --query "JWT validation" --mode hybrid --top-k 5
python -m rag.search --query "STRECK-482 acceptance criteria" \
                     --filter "ado://streck/Security/"
```

`--mode` is one of `hybrid` (default — KG + vector blend), `vector`
(pure similarity), `graph` (knowledge-graph traversal). `--filter`
applies a path-prefix filter client-side after retrieval.

### 4.2 Expected stdout

```json
{
  "query": "how does AuthService validate JWTs?",
  "mode": "hybrid",
  "top_k": 8,
  "status": "ok",
  "hits": [
    {
      "content": "def validate_token(token: str) -> Claims:\n    ...",
      "source_path": "src/lib/jwt.py",
      "span": "42-58",
      "score": 0.873,
      "citation": "[source:src/lib/jwt.py#42-58]"
    },
    {
      "content": "## JWT validation\n\nWe validate access tokens via ...",
      "source_path": "ado://streck/Security/Security.wiki/AuthFlow.md",
      "span": "10-44",
      "score": 0.812,
      "citation": "[source:ado://streck/Security/Security.wiki/AuthFlow.md#10-44]"
    }
  ]
}
```

### 4.3 Citation format

Every hit carries `citation = "[source:<source_path>#<span>]"` — the
`source:` prefix is canonical (iter-3 canonicalisation; earlier
iter-2 code shipped `[<path>#<span>]` without the prefix).
Downstream agents MUST quote the citation tag verbatim per CLAUDE.md
§6 / the fourth iron law in `agentic-rag-research/SKILL.md`:

> EVERY FACTUAL CLAIM MUST CARRY A `[source:path#span]` CITATION.
> UNCITED CLAIMS ARE DELETED.

### 4.4 From a Claude Code session

```
/rag-search how does AuthService validate JWTs?
```

`/rag-search` dispatches the `rag-researcher` subagent which runs the
autoresearch loop (see `skills/agentic-rag-research/SKILL.md`):

1. Formulate 2-4 angle queries.
2. Call `rag/search.py --query <q> --top-k 8`.
3. Read top chunks, extract facts, note gaps.
4. Generate follow-ups; loop up to depth budget (default 3).
5. Synthesize bullet report with inline `[source:path#span]` citations
   and a final "Excerpts ready for `context_excerpts`" table that maps
   each cite to a project-relative materialised file (see §6 below).

---

## 5. MCP server (Claude Code integration)

### 5.1 Start the server

```bash
just rag-mcp                      # foreground stdio
# or
python -m rag.mcp_server          # same thing
```

The server registers three FastMCP tools:

| Tool | Args | Returns |
|---|---|---|
| `rag_search` | `query: str, mode: str = "hybrid", top_k: int = 8` | JSON array of `{content, source_path, span, score, citation}` |
| `rag_ingest` | `source_uri: str` | JSON `IngestReport` |
| `rag_list_sources` | _(none)_ | JSON list of `source_path` strings |

### 5.2 Wire into Claude Code

Add to `.claude/settings.json` under your project root (or the user
settings if you want it everywhere):

```json
{
  "mcpServers": {
    "soup-rag": {
      "command": "python",
      "args": ["-m", "rag.mcp_server"],
      "env": {
        "POSTGRES_URL": "postgres://soup:soup@localhost:5432/soup_rag",
        "ANTHROPIC_API_KEY": "${env:ANTHROPIC_API_KEY}",
        "OPENAI_API_KEY": "${env:OPENAI_API_KEY}",
        "GITHUB_TOKEN": "${env:GITHUB_TOKEN}",
        "ADO_PAT": "${env:ADO_PAT}"
      }
    }
  }
}
```

Restart the Claude Code session. The tools then appear as
`mcp__soup-rag__rag_search`, `mcp__soup-rag__rag_ingest`,
`mcp__soup-rag__rag_list_sources`.

### 5.3 Verify

```
> use the soup-rag MCP server to list ingested sources
```

Claude calls `mcp__soup-rag__rag_list_sources` and prints the array.

---

## 6. Re-ingesting / updating

### 6.1 Single source

```bash
python -m rag.ingest --source github://streck/auth-service
```

The ingester re-fetches everything; dedup happens client-side via
`Chunk.hash()` (sha1 over `source_path + span + content`) and
server-side in LightRAG (document content hash). Unchanged chunks
are skipped at insert time.

> **Limitation today.** `Chunk.hash()` is in-memory only — it does
> not persist between processes. So a fresh `python -m rag.ingest`
> still re-fetches every blob; the only saving is at the LightRAG
> "do I already have this content?" gate, which spares the embedding
> call but not the network round trip. For a 1k-file repo expect
> ~30-90 s wall time per re-ingest.

### 6.2 All known sources

```bash
just rag-reindex
# or
python -m rag.ingest --reindex-all
```

Walks the LightRAG `doc_status` store, iterates known
`source_path`s, and runs `ingest_uri` on each. Output is one report
per source.

### 6.3 How often?

| Source kind | Suggested cadence | Rationale |
|---|---|---|
| ADO wiki (high-churn product team) | Daily, scheduled | Spec/wiki content shifts faster than code |
| ADO wiki (architecture / RFC) | Weekly | Slower churn |
| GitHub repo (active dev) | On every merge to main | Tied to CI; embed via a webhook (TODO) |
| GitHub repo (vendored / stable) | On version bump only | No reason to re-fetch unchanged HEAD |
| Web docs | Manual | Crawls are expensive; pin to release notes |

### 6.4 Cost

Embedding cost dominates. With OpenAI `text-embedding-3-small`
(1536-dim) at ~$0.02 / 1M tokens:

| Workload | Tokens | Cost (per ingest) |
|---|---|---|
| 1k-file backend repo | ~1M | $0.02 |
| 50-page ADO wiki | ~150k | $0.003 |
| 500-page ADO wiki | ~1.5M | $0.03 |

LightRAG also calls the LLM (Anthropic by default) for graph
construction during ingest. This is the dominant cost: on a 1M-token
ingest expect ~5-10 USD against Sonnet, less if you switch the LLM
provider via `SOUP_RAG_LLM_PROVIDER`.

---

## 7. Troubleshooting

### 7.1 `RagUnavailable: LightRAG backend not initialized`

Either `lightrag-hku` is not installed (run `uv sync` / `pip install
-e .[dev]`) or Postgres is unreachable.

- Check `docker ps | grep pg16` shows the container running.
- Check `psql $POSTGRES_URL -c 'SELECT 1'` succeeds.
- Look in stderr for the warning line `LightRAG unavailable (...)` —
  the parenthesised reason is the actual root cause.

### 7.2 `module 'pkgutil' has no attribute 'ImpImporter'`

Python 3.13 issue with old setuptools. See
`docs/runbooks/python313-pkgutil.md`.

### 7.3 Postgres container "not ready"

See `docs/runbooks/postgres-container-not-ready.md`.

### 7.4 Anthropic rate limit during heavy ingest

LightRAG fans out many graph-construction LLM calls. See
`docs/runbooks/anthropic-rate-limit.md`. Workaround: throttle ingest
to one source at a time, or switch to an OpenAI provider for the
ingest LLM (`export SOUP_RAG_LLM_PROVIDER=openai`).

### 7.5 `github tree truncated for github://streck/<repo>`

The repo has >100k tree entries. Workaround: ingest specific
subdirectories via the filesystem source instead — clone locally,
then `python -m rag.ingest --source file:///c/dev/<repo>/docs`.

### 7.6 ADO wiki returns 0 pages

- Check the wiki ID resolution: `curl -u :$ADO_PAT
  https://dev.azure.com/$ADO_ORG/$ADO_PROJECT/_apis/wiki/wikis?api-version=7.1`
- Confirm the project name matches case-sensitively.
- If the project has only a code wiki (no project wiki), today's
  adapter will silently 404 on page fetch — see TODO in
  `rag/sources/ado_wiki.py`.

### 7.7 `just rag "<query>"` fails with "argparse: --query is required"

Known bug in the `justfile` rag recipe (positional → `--query`
mapping is missing). Workaround until iter-3 fixes it:

```bash
python -m rag.search --query "<your query>"
# or
python -m rag.search -q "<your query>"
```

Same applies to `just rag-ingest "<src>"` — use
`python -m rag.ingest --source "<src>"`.

### 7.8 Stale `.soup/rag_storage/` after schema change

If you upgrade `lightrag-hku` and see deserialization errors, blow
away the working dir AND truncate the Postgres tables:

```bash
rm -rf .soup/rag_storage
psql $POSTGRES_URL -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
```

Then re-run ingest.

---

## 8. Patterns: ingest → research → context_excerpts

The full Streck-engineer flow for "build a new app that integrates
with AuthService":

```bash
# 1. one-time per project: ingest the dependencies
python -m rag.ingest --source github://streck/auth-service
python -m rag.ingest --source github://streck/streck-shared-utils
python -m rag.ingest --source ado://streck/Security/Security.wiki

# 2. interactive Claude Code session
/specify build a passwordless login UI calling streck/auth-service
/clarify
/plan
# ── plan-writer / tasks-writer dispatch rag-researcher under the
# ── agentic-rag-research skill, which writes:
# ──   .soup/research/<plan-slug>/auth-service-jwt.md
# ──   .soup/research/<plan-slug>/wi-482.md
# ── then threads them into TaskStep.context_excerpts.
/tasks
/implement
```

Inside `/tasks`, `tasks-writer` reads the rag-researcher report's
"Excerpts ready for `context_excerpts`" table and threads each
materialised path into the matching steps. The orchestrator's
`agent_factory._compose_brief` then injects the file content
verbatim under a `## Context excerpts (verbatim)` section in the
subagent's first-turn prompt — no need for the subagent to call the
RAG MCP server again.

ADO work-item references like `STRECK-482` in the spec are picked up
by `ado-agent` (see `.claude/agents/ado-agent.md`) which writes
`.soup/research/<plan-slug>/wi-482.md` for the same threading.

GitHub issue/PR references like `#482` or
`streck/auth-service#482` are handled symmetrically by
`github-agent`.

---

## 9. Reference

- `rag/client.py` — `LightRagClient`, `Chunk`, `Retrieval`,
  `IngestReport`.
- `rag/ingest.py` — chunker + `Ingester` + CLI.
- `rag/search.py` — `Searcher` + CLI + markdown rendering.
- `rag/mcp_server.py` — FastMCP server (3 tools).
- `rag/sources/github.py` — GitHub adapter.
- `rag/sources/ado_wiki.py` — ADO wiki adapter.
- `rag/sources/filesystem.py` — local FS adapter.
- `rag/sources/web_docs.py` — HTML crawler (depth-1 by default).
- `.claude/skills/agentic-rag-research/SKILL.md` — research-loop
  contract and `context_excerpts` materialisation pattern.
- `.claude/agents/rag-researcher.md` — the agent.
- `.claude/agents/docs-ingester.md` — the agent that fronts
  `/rag-ingest`.
- `.claude/agents/ado-agent.md` — work-item materialisation flow.
- `.claude/agents/github-agent.md` — issue/PR materialisation flow.
- `schemas/execution_plan.py::TaskStep.context_excerpts` — the field
  the materialised paths land in.
- `orchestrator/agent_factory.py::_compose_brief` — where the
  `context_excerpts` content gets injected at spawn time.
