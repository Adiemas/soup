# iter-2 dogfood — RAG + GitHub + ADO context pull

**Date:** 2026-04-14
**Framework under test:** `soup` at `C:\Users\ethan\AIEngineering\soup`
**User context:** Streck engineers building new apps that integrate with
existing systems. Require pulling context from ADO work items, ADO
wikis, and GitHub repos.
**Mode:** Read-mostly + scoping. TODOs added to source adapters, no
behaviour changes.

---

## Summary of current RAG capabilities

Soup ships a LightRAG-backed RAG pipeline with four source adapters
(GitHub, ADO wiki, filesystem, web docs), a sync + async Python API, a
CLI (`python -m rag.ingest|search`), a FastMCP server, and two
`/rag-ingest` + `/rag-search` slash commands fronted by the
`docs-ingester` and `rag-researcher` subagents. Retrievals return
`[source_path#span]` citations and flow through `Retrieval.build`, which
stamps the tag at construction.

What works today, end-to-end, on a fresh install with `ADO_PAT` and
`GITHUB_TOKEN` set:

- Ingesting a public or private GitHub repo's text blobs via REST API
  with a PAT (extension allow-list, 1.5 MB blob cap, sha1-based
  in-memory dedup).
- Ingesting a single ADO project wiki (picks `values[0]` from the wiki
  list endpoint; flattens nested pages via `subPages`).
- Hybrid / vector / graph search through LightRAG's `mix` / `naive` /
  `global` modes.
- Cited markdown rendering of hits via `Searcher.render_markdown`.
- MCP tool exposure (`rag_search`, `rag_ingest`, `rag_list_sources`)
  for Claude Code + any MCP client.
- Autoresearch loop (`rag-researcher` agent + `agentic-rag-research`
  skill): 2-4 angle queries, iterative follow-ups, budget-capped,
  citation-required synthesis.
- Context injection into spawned subagents via
  `TaskStep.context_excerpts` + `spec_refs`, resolved at
  brief-compose time in `agent_factory._compose_brief` with markdown
  anchor + `path:line-from-line-to` support.

What the pipeline does NOT do today (detail in "Critical gaps"):

- Ingest ADO work items or GitHub issues/PRs.
- Distinguish ADO code wikis vs project wikis.
- Respect `.gitignore` on GitHub repos.
- Persist cross-process dedup (re-ingest pays full network cost).
- Auto-materialise RAG citations into `context_excerpts` (the
  researcher returns URI-shaped cites like
  `[github://streck/auth-service/src/lib/jwt.py#42-58]` but
  `agent_factory._safe_relative_path` rejects URI schemes).

---

## End-to-end walkthrough (GitHub + ADO)

Target scenario: _"Streck engineer installs soup on a Windows laptop,
ingests `streck/auth-service`, `streck/frontend`, `streck/backend`, and
the `Security` ADO wiki, then runs `/rag-search` and has the results
flow into the next `/plan` + `/tasks` cycle."_

### Cold install → first query (15 minutes, best case)

```bash
# 1. bootstrap
winget install Python.Python.3.12 astral-sh.uv Docker.DockerDesktop Casey.Just
git clone <soup-repo> C:\dev\soup
cd C:\dev\soup
cp .env.example .env
# edit .env: ANTHROPIC_API_KEY, OPENAI_API_KEY, POSTGRES_URL,
#           GITHUB_TOKEN, ADO_ORG, ADO_PROJECT, ADO_PAT
just init                  # venv + postgres container + hooks

# 2. ingest
python -m rag.ingest --source github://streck/auth-service
python -m rag.ingest --source github://streck/frontend
python -m rag.ingest --source github://streck/backend
python -m rag.ingest --source ado://streck/Security

# 3. query
python -m rag.search --query "how does AuthService validate JWTs?"
```

Expected runtime:

| Step | Dominant cost | Wall time |
|---|---|---|
| `just init` | docker pull pgvector:pg16 | 2-5 min |
| 3x `rag.ingest` github | LightRAG graph-construction LLM calls | 5-15 min each |
| 1x `rag.ingest` ado-wiki | ADO API + graph-construction | 2-10 min |
| 1x `rag.search` | two LightRAG LLM round-trips | 10-30 s |

### Where this breaks down on first contact

1. **No docs.** Until this PR, there was no user-facing guide. The
   `rag/README.md` covers Python API only; nothing on MCP registration,
   nothing on PAT scopes, nothing on re-ingest cadence, nothing on
   troubleshooting PAT scope errors.
2. **`just rag …` recipes are broken.** The positional args are not
   prefixed with `--query`/`--source` so `python -m rag.search
   <query>` fails with `argparse: --query/-q is required`. Users must
   learn to invoke the module directly.
3. **`.env` doesn't flow into `python -c`** invocations, so
   troubleshooting from cmd.exe shells is confusing (works in Claude
   Code sessions because `session_start.py` loads it; doesn't work
   from a bare shell).
4. **No scheduled re-ingest.** Nothing in the justfile, `.claude/`, or
   docker-compose runs `rag.ingest --reindex-all` on a cron. Stale
   corpora are a matter of time.
5. **`OPENAI_API_KEY` is required for embeddings** but is not listed
   in `.env.example`. LightRAG defaults to OpenAI embeddings
   (`openai_embed`, 1536-dim); a user who sets only `ANTHROPIC_API_KEY`
   will get a `RagUnavailable` on ingest and won't know why without
   reading `rag/client.py::_pick_embedding_func`.
6. **No wiki discovery UX.** To find the right ADO wiki ID, the user
   has to `curl` the `wikis` endpoint by hand — there is no
   `python -m rag.sources.ado_wiki list-wikis --org streck` helper.

---

## Critical gaps (ranked)

### CRITICAL

**C1. `OPENAI_API_KEY` is required for embeddings but absent from
`.env.example`.** The default embedding func is `openai_embed`; with no
key, `LightRagClient._pick_embedding_func` completes but the first
embed call raises a cryptic "api key not set" error from the openai
SDK. **Fix**: add `OPENAI_API_KEY=` to `.env.example` with a comment;
mention it in `rag/README.md` and (done in this PR) the user guide.

**C2. ADO work items are not a first-class RAG source.** The user
story explicitly calls out "pull context from ADO work items/wikis"
but only wikis are wired. A spec that mentions `STRECK-482` cannot be
auto-resolved by soup today — there is no `ado-wi://` scheme, no
`AdoWorkItemsSource`, no flow in `plan-writer`/`tasks-writer` to
grep for work-item refs and materialise them. **Fix:** add
`AdoWorkItemsSource` keyed by WIQL query and a materialisation path
described in the updated `ado-agent.md` (done in this PR as scoping;
code in iter-3).

**C3. `just rag` / `just rag-ingest` recipes don't map positionals
to flags.** `python -m rag.search "<query>"` fails because argparse
expects `--query`. Every user hits this within their first 30
seconds. **Fix:** change `justfile` to
`python -m rag.search --query "{{query}}"` and
`python -m rag.ingest --source "{{source}}"`.

### HIGH

**H1. No cross-process dedup for re-ingest.** `Chunk.hash()` is an
in-memory set on the `LightRagClient` instance; every `python -m
rag.ingest` is a fresh process, so the set is empty. LightRAG's
document content hash saves the embedding call but not the network
round-trip. On a 1k-file repo this is ~30-90 s of wasted fetching per
re-ingest. **Fix:** persist a `(source_uri, path) → sha` table in
Postgres (can reuse LightRAG's `doc_status` table) and short-circuit
at the adapter layer before `fetch_blob` / `fetch_page`.

**H2. GitHub adapter ingests issues + PRs 0%.** A spec that says "see
the thread in `streck/auth-service#482`" has no RAG path. **Fix:**
iter-3 add `github://owner/repo/issues/<N>` and
`github://owner/repo/pulls/<N>` URIs to `Ingester.build_source`, plus
issue/PR fetch in `github.py::iter_chunks`.

**H3. RAG URIs can't flow into `context_excerpts` directly.**
`agent_factory._safe_relative_path` rejects anything with a `://`, so
a citation like `[github://streck/auth-service/src/lib/jwt.py#42-58]`
coming back from `rag-researcher` cannot be threaded into
`TaskStep.context_excerpts` — it fails `TaskStep._relative_paths_only`
at parse time. The researcher must materialise the snippet to
`.soup/research/<slug>/*.md` first, then reference that local path.
**Fix (scoped in this PR):** added the "Excerpts ready for
`context_excerpts`" output contract in the
`agentic-rag-research/SKILL.md` and the `rag-researcher.md` agent.
Iter-3 should wire an orchestrator helper
(`rag/materialise.py::materialise_retrieval(...)`) so the pattern
isn't a hand-rolled chore per task.

**H4. Code wiki vs project wiki.** `AdoWikiSource` does not distinguish
the two. Code wikis are git-backed and need `versionDescriptor` on
every page fetch; we silently 404 on non-default branches. Streck has
both kinds in production. **Fix:** detect the wiki `type` field; set
`versionDescriptor` accordingly.

### MEDIUM

**M1. No `.gitignore` respect for `GithubRepoSource`.** A private repo
with a checked-in `.env` or `secrets/credentials.json` would NOT be
blocked today only because `.env` isn't in the extension allow-list.
That's accidental safety, not design. **Fix:** parse repo
`.gitignore` (or honour a second `ignore_globs` on the adapter) and
skip matching paths explicitly.

**M2. No attachment handling for ADO wikis.** PDFs and architecture
diagrams are dropped on the floor. Retrieved chunks lose visual
context. **Fix:** fetch attachments to
`.soup/rag_storage/attachments/<wiki>/<name>` and keep the inline
markdown reference.

**M3. Truncated git trees silently lose tail entries.** For
`streck/frontend` (typical monorepo size) this rarely bites, but a
repo with >100k tree entries (yarn workspaces, checked-in build
output) loses the tail. **Fix:** on `truncated: true`, fall back to
per-subdir tree fetches.

**M4. Wiki ID auto-discovery picks `values[0]`.** For projects with
multiple wikis this silently ingests the wrong one. **Fix:** emit a
warning when `len(values) > 1` and require explicit `wiki_id` in that
case; add a `list-wikis` CLI.

**M5. No scheduled re-ingest.** A Streck user who ingests the
Security wiki on day 1 is querying stale content on day 90. **Fix:**
ship a `justfile` recipe + a GitHub Actions / pipelines example that
runs `just rag-reindex` nightly.

**M6. `OPENAI_API_KEY` not in `.env.example`** already covered in C1
but also relevant here: the env-var omission cascades into the
embedding contract. If Streck's security posture disallows OpenAI,
we need a swap-in embedding provider (Anthropic embeddings? Cohere?
Local bge-m3?). LightRAG supports it — soup's `client.py` does not
currently route it through env.

### LOW

**L1. `rag.search --filter` is a client-side path-prefix string
match.** It cannot, say, `source_prefix=github://streck/auth-service`
be combined with `mode=hybrid` in a way that pushes the filter into
LightRAG's vector query. For most use cases this is fine; for large
indexes it wastes LLM tokens on hits you'd discard anyway. **Fix:**
pre-filter at the doc-status layer.

**L2. Research-loop citation format drifts.** `rag-researcher.md`
documents `[source:path#span]` with a `source:` prefix; `Retrieval.build`
emits `[path#span]` with no prefix. Downstream validators don't care,
but it's a minor doc-vs-code drift.

**L3. MCP server registration docs scattered.** The flow (add
`mcpServers` block to `.claude/settings.json`, restart Claude Code) is
not in `rag/README.md`; this PR's user guide is the first
consolidated write-up.

**L4. No rate-limit handling on GitHub blob fetches.** 60 req/h
anonymous and 5000 req/h authenticated; a 1k-file repo at
~1 req/blob will trip the authenticated bucket on a heavy day. The
adapter logs a debug line and returns `None` on 403. **Fix:** add
exponential backoff with jitter, or batch via GraphQL.

**L5. No MCP resource (vs tool) exposure.** FastMCP supports
`@mcp.resource()` for read-only, introspectable URIs. Soup could
expose `soup://sources`, `soup://sources/<uri>` as resources so a
client can browse what's indexed without a tool call. Cosmetic but
useful UX.

---

## Subtle UX gaps (onboarding, docs, error messages)

1. **"Stub-safe" is under-documented.** `.env.example` says integrations
   are stub-safe, but a user with empty `GITHUB_TOKEN` who runs
   `rag.ingest --source github://streck/private-repo` gets a flurry of
   `blob fetch failed: 404` warnings in stderr and a
   `chunks_inserted: 0` report with zero errors in the JSON. Looks
   like success. **Fix:** when `GITHUB_TOKEN` is absent and >N blobs
   fail, surface a single actionable error in the `IngestReport.errors`
   array.

2. **`RagUnavailable` is not user-friendly.** The exception message is
   the original exception repr, which is often a pgvector DSN error or
   a `lightrag_hku` import error. Users get no hint about whether to
   start docker or `pip install` something. **Fix:** catch common
   exceptions in `_build_lightrag` and map to actionable messages
   (link to `docs/runbooks/postgres-container-not-ready.md`, link to
   the install instructions).

3. **Wiki ID "Security.wiki" vs "Security" is ambiguous.** Users type
   either; the API expects the wiki's GUID _or_ `<project>.wiki`
   format. The adapter accepts both paths, but no docs say which to
   use when. **Fix:** explicit note in user guide (done) and accept
   the project's wiki canonical name in `_resolve_wiki_id`.

4. **`/rag-search` emits a markdown blob but `/rag-ingest` emits raw
   JSON.** Asymmetry. The user guide now documents both, but the
   command specs themselves should agree on format (markdown for
   interactive, JSON only behind `--json`).

5. **`rag-researcher` has no loop-break on empty corpus.** If nothing
   is ingested, the researcher still runs the depth-budget loops,
   each returning an `<llm-answer>` synthetic hit and burning LLM
   tokens. **Fix:** short-circuit when `list_sources()` is empty.

6. **`docs-ingester` agent doc says it calls `rag/ingest.py --source
   <descriptor>` with descriptors like `github:<owner>/<repo>`, but
   the actual scheme is `github://<owner>/<repo>`.** Colon vs
   colon-slash-slash. **Fix:** align the agent doc with the code
   (done in this PR in the user guide; agent file still has legacy
   shape — leave alone per scope, but flag).

7. **Citation tag format inconsistency:** researcher instructions
   say `[source:path#span]`, client emits `[path#span]`. Downstream
   `tasks-writer` doesn't check, but a strict "every claim cited"
   validator would reject legitimate hits. **Fix:** pick one.

8. **Session start doesn't check RAG readiness.** `session_start.py`
   does not verify Postgres is reachable or that there are any ingested
   sources. A session happily runs `/rag-search` against an empty
   index and returns a `<llm-answer>`-only retrieval that looks valid
   but cites nothing real. **Fix:** a RAG-readiness section in the
   additionalContext (count of sources, last-ingest timestamp).

---

## Proposed soup additions (iter-3)

Ranked by leverage for Streck's "build a new app that integrates with
existing systems" user story.

### P1. `AdoWorkItemsSource` + `ado-wi://` URI scheme

New source adapter keyed by WIQL query. `Ingester.build_source`
routes `ado-wi://org/project?wiql=<url-encoded>` to it. Makes
`ado-agent`'s work-item materialisation an actual RAG-backed flow
rather than a bespoke shell command per reference.

### P2. `rag/materialise.py` helper

A function
`materialise_retrieval(retrieval: Retrieval, *, plan_slug: str) -> Path`
that writes the retrieval to
`.soup/research/<plan-slug>/<source-slug>.md` with a provenance
header, and returns the repo-relative path ready to drop into
`TaskStep.context_excerpts`. Makes the "RAG URI → local path" bridge
a one-liner for the researcher.

### P3. `soup ingest-cron` / `just rag-cron` justfile recipe

Ships an opinionated "re-ingest every source in the manifest once a
day" recipe + a sample GitHub Actions workflow and an ADO pipeline
YAML. Solves the stale-corpus problem operationally.

### P4. Persistent dedup via `rag_ingest_seen` table

A Postgres table `(source_uri, path, content_sha1)` populated by the
adapter before it calls `fetch_blob`/`fetch_page`. Cuts re-ingest
network cost by ~90% on unchanged repos.

### P5. `.gitignore` respect in `GithubRepoSource`

Parse repo `.gitignore` via GitHub's blob API or local clone;
pre-filter the tree. Defense-in-depth against checked-in secrets.
Similar pattern for `FilesystemSource` (already has `ignores` but no
gitignore integration).

### P6. `AdoWikiSource` code-wiki support

Detect wiki `type` from the list endpoint; route page fetches with a
`versionDescriptor` when `type == "codeWiki"`. Also: `list-wikis`
CLI helper.

### P7. Issue + PR ingestion for GitHub

`github://owner/repo/issues/<N>` + `github://owner/repo/pulls/<N>`
schemes. Ingest body + comments + linked artifacts. Makes
`rag-researcher` competent on discussion threads.

### P8. RAG-readiness line in `session_start.py`

One-liner in `additionalContext` showing "RAG: 4 sources indexed,
last ingest 6h ago." If zero sources, warn loudly.

### P9. MCP resource exposure (`soup://sources`, `soup://sources/<uri>`)

Read-only URIs so a Claude Code client can browse indexed sources
via introspection, without calling `rag_list_sources` as a tool.

### P10. `rag_agents` discoverability — auto-register ingested repos'
`AGENTS.md` / `CLAUDE.md` with `agent-finder`

When soup ingests a repo that has its own `AGENTS.md` or
`.claude/agents/`, copy the agent descriptions into
`library.yaml` under a `discovered_from: github://...` group so
`/plan` can consider them as candidate roles. Helps brownfield
integration (the warhammer-40k-calculator dogfood showed this was
the single biggest onboarding tax).

### P11. Embedding provider swap via env

`SOUP_RAG_EMBED_PROVIDER` = `openai` (default) | `anthropic` |
`cohere` | `local-bge`. Matters for Streck security review of
outbound API calls.

### P12. Citation-format canonicalisation

Pick one: `[path#span]` (current `Retrieval.build`) or
`[source:path#span]` (current `rag-researcher.md`). Add a `Citation`
helper in `rag/client.py` that validates + renders consistently, and
update every agent/skill that references the format. Low effort,
closes a drift that will embarrass us when we ship audit logs.

---

## Deliverables written

- `docs/USER_GUIDE_RAG.md` — new, ~500 lines, covers prerequisites,
  GitHub + ADO ingest, query, MCP, re-ingest cadence + cost,
  troubleshooting, patterns.
- `rag/sources/ado_wiki.py` — added 6 scoping TODOs at module + class
  docstring (code-wiki, attachments, wiki discovery, work items,
  incremental, pagination). No behaviour change.
- `rag/sources/github.py` — added 6 scoping TODOs (`.gitignore`,
  issues+PRs, topology weight, incremental, pagination, GHE). No
  behaviour change.
- `.claude/skills/agentic-rag-research/SKILL.md` — new section
  "Feeding research into `TaskStep.context_excerpts`" + output
  contract for "Excerpts ready for `context_excerpts`" table.
- `.claude/agents/rag-researcher.md` — output section now requires
  the excerpts table.
- `.claude/agents/ado-agent.md` — new "Auto-pulling work items into
  `TaskStep.context_excerpts`" section with file-shape contract.
- `.claude/agents/github-agent.md` — symmetric "Auto-pulling issues /
  PRs" section.

## Deliverables NOT written (out of scope)

- No edits to `orchestrator/`, `schemas/`, `cli.py`.
- Did not implement any of P1-P12; all deferred to iter-3.
- Did not fix the `justfile` `rag` / `rag-ingest` recipes — that's a
  behaviour change on a user-facing command. Flagged as C3.
