---
description: Add a source (github-repo, ado-wiki, filesystem-path, web-url) to the RAG index.
argument-hint: "<source-uri>"
---

# /rag-ingest

## Purpose
Incrementally index a new source into the RAG backing store. Idempotent — re-ingest updates changed chunks only.

## Variables
- `$ARGUMENTS` — source URI; required. Supported schemes:
  - `github://<owner>/<repo>[@<branch>]` → GithubRepoSource
  - `ado-wiki://<org>/<project>/<wiki>` → AdoWikiSource
  - `file://<abs-path>` or plain path → FilesystemSource
  - `https://...` → WebDocsSource

## Workflow
1. Invoke `docs-ingester` agent with the URI.
2. Agent dispatches to appropriate adapter in `rag/sources/`.
3. Adapter streams chunks; `rag/ingest.py::Ingester` writes to LightRAG (Postgres).
4. Emit `IngestReport`:
   - Source URI + adapter used.
   - Documents seen / chunks written / duplicates skipped.
   - Duration + warnings (missing creds, binary skips, etc.).
5. Register source in `.soup/rag-sources.json` (append-only log).

## Output
- Ingest report JSON path.
- Human-readable summary.
- Suggested next: `/rag-search "<related query>"`.

## Notes
- Large repos: consider `--glob` filter (handled inside FilesystemSource config).
- Missing `GITHUB_TOKEN` / `ADO_PAT`: adapter logs warning, attempts anonymous (public repos only), may fail.
- Never log document contents; only metadata + counts.
