# Dogfood: soup vs `claude-news-aggregator`

Date: 2026-04-14
Target: `C:\Users\ethan\Personal-Projects\claude-news-aggregator`
Framework under test: `C:\Users\ethan\AIEngineering\soup`
Mode: propose-only, read-mostly.

## Target snapshot

- **Type:** Pure TypeScript *script* (no backend service, no frontend, no DB). A scheduled GitHub Actions job runs `tsx src/index.ts` once per week and commits state back to a `state` git branch.
- **Stack:** Node 22+, pnpm 10.33 (via corepack), `@anthropic-ai/sdk`, `rss-parser`, `cheerio`, `@mozilla/readability`, `jsdom`, `undici`, `zod`, `vitest`. Three vendors total: GitHub, Anthropic, Slack.
- **Modules:** `src/{ingest,enrich,state,deliver,ops}` plus `config.ts`, `index.ts`, `sources.yaml`, `team_context.md`. Tests: 9 vitest suites. Scripts: `digest-dry-run`, `backfill`, `reenrich`, `verify-sources`.
- **State:** JSON file (`seen.json`) + markdown archives, persisted on a dedicated `state` git branch. Atomic write via tmpfile + rename; write serialization guaranteed by GHA `concurrency: weekly-digest`.
- **Ingest contract:** `Adapter { fetch(source, ctx): Promise<RawItem[]> }` dispatched by `adapterFor(kind)` for `rss | api | html` — see `src/ingest/adapters.ts:28-30, 402-411`.
- **Security:** Multi-layer prompt-injection defenses (pre-prompt sanitize → Zod → verbatim-substring enforcement → pre-Slack sanitizer). `.gitleaks.toml` adds Anthropic + Slack webhook rules on top of gitleaks defaults.
- **TS strictness:** `noUncheckedIndexedAccess`, `noImplicitReturns`, `noUnusedLocals/Parameters` all on.
- **.claude/ surface:** Minimal — `.claude/settings.local.json` only, allowing `gh auth:*`, `gh repo:*`, `git push:*`. No `agents/`, no `skills/`, no `commands/`, no `hooks/`.
- **Plan artifacts:** Five rounds of architecture in `plan/` (v1 → round1 → v2 → round2 → round4 → v3-final.md). This is the project's own spec-driven history, predating any soup flow.
- **preview.md:** Current dry-run output — 13 sources, 1589 scanned, 10 posted, all in `stub` enrichment mode. No failing test or flaky pattern noted; the artifact is well-behaved.

## Existing `.claude/` setup vs soup

| Surface | `claude-news-aggregator` | soup | Gap direction |
|---|---|---|---|
| Agents | **none** | 23 agents incl. `orchestrator`, `meta-prompter`, `ts-dev`, `test-engineer`, `code-reviewer`, `security-scanner`, `verifier`, `researcher`, `rag-researcher` | soup is strictly richer — nothing to learn from target here |
| Commands | **none** | 15 commands (`/specify`, `/clarify`, `/plan`, `/tasks`, `/implement`, `/verify`, `/quick`, `/map-codebase`, `/rag-*`, etc.) | soup richer |
| Skills | **none** (uses plugin superpowers implicitly) | 14 skills incl. `tdd`, `systematic-debugging`, `brainstorming`, `spec-driven-development`, `agentic-rag-research` | soup richer |
| Hooks | **none** | `session_start`, `pre_tool_use`, `post_tool_use`, `user_prompt_submit`, `subagent_start`, `stop` — full lifecycle | soup richer |
| Settings.local permissions | Narrow allow-list: `Bash(gh auth:*)`, `Bash(gh repo:*)`, `Bash(git push:*)` — surgical | soup has deny-list for `curl/wget/nc/...` and denies `find -delete` (see `rules/global/security.md §5`) | **soup direction:** allow-lists this narrow are a worth-copying pattern for restricted-surface projects |
| Planning artifacts | `plan/` with explicit rounds + red-team + gaps critic + over-engineered critic | `.soup/plans/<slug>.md` single-doc + `specs/<name>.md` | **Lesson for soup:** this repo's **multi-round red-team + radical-simplification critic** is stronger than soup's single-pass `architect → plan-writer`. Worth adopting as a `/plan --red-team` mode or a new `red-team-critic` agent. |
| Gitleaks integration | Repo-level `.gitleaks.toml` with custom rules for Anthropic keys + Slack webhooks + path allowlist | `rules/global/security.md §2` mentions gitleaks generically but there is no repo-level `.gitleaks.toml` committed and no hook that consumes one | **soup direction:** ship a template `.gitleaks.toml` and have `security-scanner` agent read it; target repo's config is a good starting point. |
| Enrichment-mode envvar (`stub/off/live`) | `ENRICHMENT_MODE` lets the full pipeline run end-to-end with zero LLM spend — test fixture pattern at the system level | soup has no analogue; CI integration tests would benefit from a similar stub-mode convention | **soup direction:** adopt an "enrichment-mode" pattern name for integration-test-safe LLM stubs. |
| State persistence | Git branch as database (`state` branch, `seen.json`, archives) | No pattern — soup assumes Postgres | **soup gap:** a "git-as-DB" rule/template would materially help this class of repo. |

**Crucial finding:** the target's `.claude/` is trivial — but the target doesn't *need* most of what soup provides (it's a 9-test single-binary script). The collision is elsewhere: soup's **templates, rules, and roster all assume a backend with a DB and migrations**, which does not match this target.

## Scenarios

### A — Feature: add a Hacker News adapter to the existing fetcher contract

**Goal:** add a new `Source { kind: 'hn', ... }` with a matching adapter that conforms to `Adapter { fetch(source, ctx): Promise<RawItem[]> }`, or extend the existing `apiAdapter` host-dispatch (already handles `hn.algolia.com` at line 108).

Walking the soup flow:

1. **`/specify`** — invokes `spec-writer` which demands EARS-format user outcomes and the 7 sections. Friction: the target's `plan/v3-final.md` and `src/ingest/adapters.ts` already *describe the contract*, but `/specify` currently treats the contract as an unknown and asks me to restate it in user-facing outcomes. A 2-word tweak — instructing `spec-writer` to run `researcher` first when a repo already has `plan/` or architecture docs — would save a round-trip. **Gap: `/specify` has no "I'm extending an existing contract" fast path.**

2. **`/clarify`** — probably OK; this is genuinely additive.

3. **`/plan`** — invokes `architect` (opus) + `plan-writer` (sonnet). Both are good fits. The architect would correctly identify `apiAdapter.parseHnAlgolia` (already exists!) vs a new adapter as the decision. **But** the `tasks-writer` downstream will want `rules/postgres/*` and `rules/python/*` — neither applies. The TS rules path (`rules/typescript/coding-standards.md`) *does* apply. This is fine only because soup has a TS rules file — but the repo-specific things (`rss-parser`, `undici`, the dedup-key + fingerprint pair) are not encoded anywhere in soup.

4. **`/tasks` → `meta-prompter`** — decomposition question: does it order `test-engineer` before `ts-dev`? Yes, per the `meta-prompter.md` iron law "TDD-shaped: test-engineer step precedes every implementer step for the same scope." For an HN adapter the test would assert `RawItem[]` shape given a fixture HTTP response. **Concern:** `test-engineer` will need the `RawItem` interface. Fresh-context means it must re-read `src/ingest/adapters.ts` itself; soup's handoff contract (the ExecutionPlan JSON) passes `files_allowed` but not a condensed "prior-art excerpt." That is a real fresh-context loss. **Gap: plan payload should include excerpts of contract-level types referenced, not just file globs.**

5. **`researcher`** — would handle "find the fetcher interface" well (10-search budget, outputs a findings table with file|line|excerpt). For a file as clean as `adapters.ts`, this is fine. For bigger repos this budget is tight — the repo has 1 adapter file, but a bigger TS service could easily exceed.

6. **`/implement`** — `ts-dev` agent is present and correctly scoped; `tsconfig.json`'s strictness matches `rules/typescript/coding-standards.md §1` almost exactly.

7. **`/verify`** — `qa-orchestrator` dispatches `code-reviewer` + `security-scanner` + `verifier`. The existing `pnpm lint && pnpm typecheck && pnpm test` pipeline is a natural `verify_cmd`. But `verifier` expects to `just test`; there's no justfile. **Gap: verifier must accept a user-supplied `verify_cmd` and not presume `just`.**

Verdict: **works, but leaky at the edges** — `/specify` over-specs existing contracts, plan payload loses contract shape across fresh contexts, `verifier` presumes a justfile.

### B — Debugging: dedup races (the stated scenario — `preview.md` shows no active failure)

**Root-cause walk using `systematic-debugging`:**

1. **Evidence first.** Current behavior: two writers could hit `seen.json` concurrently. Except — they can't. `.github/workflows/weekly-digest.yml` has `concurrency: weekly-digest` and `writeSeenState` does tmpfile+rename (`state/write.ts:39-42`). Locally, the only failure mode is running two `pnpm digest` processes in parallel. So the scenario is **hypothetical** — the real defense is at the GHA orchestration layer, not the code.

2. **Would soup's `systematic-debugging` skill lead here?** Yes: it insists on reproducing first. A reproduction would require two processes, which would expose that GHA concurrency is the load-bearing defense. Good.

3. **But:** once we suspect `seen.json` races, the soup rules don't give us `timestamptz` / `NULLS NOT DISTINCT` advice (because no Postgres). What soup *would* give is nothing specific to JSON-file state. That's the gap: soup has no "state-file" or "git-branch-as-DB" rule set. The read/write module here implements canonical patterns (atomic rename, defensive revalidation before commit, `concurrency:` group at workflow level) that deserve to be codified.

4. **Dedup logic itself** (`src/ingest/dedup.ts`) is sound: two-key strategy (`dedupeKey(source|externalId)` + `contentFingerprint(canonicalUrl||normalizedTitle)`) directly addresses cross-source double-posting (a HN link to an Anthropic blog appears twice). This is red-team-hardened (round4/01 HIGH #3). **Soup has no dedup-pattern rule** either — another gap given how common this is in aggregators.

5. **Where systematic-debugging breaks down:** for an intermittent-on-CI-only race, needing to reproduce requires GHA-specific tooling. Soup has no `gha-replayer` utility. `github-agent` might help but is a generic wrapper. A workflow-replay helper would be a genuine soup addition.

### C — Refactor: JSON files → SQLite

**What it touches:**

- `src/state/{read,write,types,index}.ts` — fully rewritten against a SQLite driver (`better-sqlite3` likely).
- Schema for two tables: `seen_items`, `stats`. Indexes on `dedupe_key`, `content_fingerprint`, `first_seen_at`.
- `package.json` — new dep.
- `.github/workflows/weekly-digest.yml` — the state-branch checkout stays (SQLite DB file still committed there); may need LFS for large DBs.
- `scripts/backfill.ts`, `scripts/reenrich.ts` — both call state read/write; signatures can stay but internals change.
- **Characterization tests** (brownfield.md §1 — good!): snapshot current `seen.json` behavior before cutover. Soup's `rules/global/brownfield.md` forces exactly this: "Write a regression test that captures the CURRENT observed behavior BEFORE you change it." That's well-aligned.

**Does `rules/postgres/migrations.md` help?** **No.** It is Postgres-specific — `CONCURRENTLY`, `NULLS NOT DISTINCT`, `pg_stat_statements`, EF Core retry, Alembic — none of which apply. **Gap:** soup needs a `rules/sqlite/migrations.md` or a generic `rules/migrations/` that covers WAL mode, `PRAGMA foreign_keys=ON`, single-writer-many-reader concurrency model, and the fact that SQLite `ALTER TABLE` is limited (must re-create tables for column drops). The Postgres file mentions `expand/contract` (§6a) which actually *does* translate — but the reader has to do the translation work themselves.

**Does `brownfield.md` force the right characterization tests?** Yes — §1-6 of the iron law nail it: read first, enumerate callers, write regression test, then change. The target already has `tests/state.test.ts` as a seed. Soup's brownfield rule would correctly refuse to let `implementer` touch `state/` until a characterization test captures: "reading a well-formed `seen.json` returns SeenState with N items", "dedupeKey lookup is O(1) by design," "first-seen-at monotonicity" etc.

**Open gap on refactor:** soup has no **data-migration / backfill** rule. Moving JSON → SQLite is a one-time data migration; the Postgres rule §10 covers data migrations but presumes Alembic. A stack-agnostic data-migration rule would cover both.

## Concrete soup gaps surfaced

1. **pnpm** (re-confirmed from prior dogfood). Target uses `pnpm@10.33.0` via corepack + `--frozen-lockfile`. Soup templates/rules mention `npm` (in a couple of dogfood traces) and `npm audit`. No pnpm guidance; no lockfile-enforcement rule.
2. **Pure TS-service template gap.** Soup has `react-ts-vite` (frontend) and no backend-less TS template. A `ts-node-script` or `ts-scheduled-job` template is missing. The target is archetypal for this slot: `tsx src/index.ts` as entrypoint, strict tsconfig, zod at boundaries, vitest colocated.
3. **State-persistence pattern gap.** No rule/template for JSON-file state, git-as-DB, or SQLite. All three are common; Postgres is not always the right tool.
4. **Gitleaks alignment.** Soup has a `security-scanner` agent and mentions gitleaks in `rules/global/security.md §2.4` but no committed `.gitleaks.toml` in soup templates. Target ships a custom `.gitleaks.toml` with Anthropic + Slack webhook regexes and path allowlists — exactly the kind of artifact soup should standardize on. Soup's pre-commit scanner should consume the repo-level TOML, not run with defaults.
5. **Harmonization of `.claude/settings.local.json` narrow allow-lists.** Target's 3-permission allow-list (`gh auth:*`, `gh repo:*`, `git push:*`) is the kind of minimal surface a restricted-scope repo wants. Soup's settings are more permissive. A `restricted-scope` preset in soup's settings would help.
6. **Fresh-context loss on contract-reference tasks.** `meta-prompter`'s ExecutionPlan JSON carries `files_allowed` globs but not **contract excerpts**. When `test-engineer` and `ts-dev` are two fresh contexts both needing to know `RawItem`, they each re-read. Add a `context_excerpts: [{file, lines, why}]` field.
7. **RAG source adapter for TS projects.** `rag/sources/` has `filesystem.py`, `github.py`, `web_docs.py`, `ado_wiki.py`. A TS-aware ingester that understands `tsconfig.json`, `package.json` dependency graphs, and `*.test.ts` colocation would improve retrieval quality for repos of this shape.
8. **Red-team / radical-simplification critic pass.** The target's `plan/round4/01-red-team.md` and `round4/03-over-engineered.md` are a stronger planning loop than soup's single `architect + plan-writer` pass. Soup should adopt a **`red-team-critic` agent** and an **`over-eng-critic` agent** invoked by `/plan --rigorous` or a new `/plan-rounds` command.
9. **`verifier` hard-codes `just test`.** Should read `verify_cmd` from the plan and fall back to `just test` only if declared. Target uses `pnpm test`.
10. **Enrichment-mode / stub-mode integration-test pattern.** Target's `ENRICHMENT_MODE=stub` is a great pattern for zero-cost CI; soup has no named analogue. A rule entry encoding this pattern ("every LLM-touching path ships a stub mode, parameterized by env var, default-on in CI") would be widely useful.

## Lessons for soup from this repo's own patterns

- **Plan-by-rounds (v1 → critics → v2 → red-team → v3-final).** Soup's linear flow benefits from being optional-multi-round. Add a `/plan --rounds N` variant that invokes critic agents (cost, security, over-eng, red-team) between drafts.
- **Stub-mode across expensive dependencies.** Encode as a soup rule.
- **Concurrency at the workflow boundary, not the code.** Target avoids N bugs by declaring `concurrency: weekly-digest` in GHA and letting the runtime serialize. Soup's rules don't document this pattern; they should.
- **`.gitleaks.toml` as committed artifact.** Copy the target's shape as a template.
- **Narrow-scope `settings.local.json` allow-lists.** Offer as a preset.
- **Two-key dedup for aggregator-shaped workloads.** Source-id + canonical-fingerprint. Template this.
- **Markdown archives as a queryable audit log** (`archive/YYYY-WW.md` committed to a branch). Alternative to DB-backed audit tables; document as a legitimate choice.

## Proposed soup additions (file-level, concrete)

1. **`templates/ts-node-script/`** — new template matching this target's shape.
   - `package.json` with `pnpm@10`, `tsx`, `vitest`, `zod`, `typescript` strict; `scripts.{test,lint,typecheck,build,dry-run}`.
   - `tsconfig.json` mirroring target strictness.
   - `eslint.config.js` flat config.
   - `CLAUDE.md` with stack-specific steering.
   - `src/index.ts` skeleton + `src/config.ts` env-schema with zod.
   - `.gitleaks.toml` starter.
   - `.github/workflows/{ci.yml,scheduled.yml}` with `concurrency:` group.
   - `scripts/dry-run.ts` pattern.
2. **`rules/typescript/pnpm.md`** — lockfile enforcement, `--frozen-lockfile` in CI, `packageManager` field, corepack bootstrap, Windows EPERM note (target's README line 69 is a nice artifact to cite).
3. **`rules/state-persistence/`** — new rules dir with `json-file.md`, `sqlite.md`, and `git-branch-as-db.md`. Cover atomic write (tmpfile+rename), defensive revalidation before commit, concurrency-via-workflow-boundary, backup cadence, SQLite WAL + `PRAGMA`.
4. **`rules/global/gitleaks.md`** — canonical `.gitleaks.toml` starter + rule that `security-scanner` must read the repo-level TOML, not run with defaults. Copy target's Anthropic + Slack webhook regexes.
5. **`.claude/agents/red-team-critic.md`** + **`.claude/agents/over-eng-critic.md`** — new critic roles invoked between `architect` and `plan-writer` when `/plan --rounds` is requested. Each produces a critique doc (`.soup/plans/<slug>.critic.<kind>.md`) that `plan-writer` must address.
6. **`rag/sources/typescript.py`** — TS-aware ingester (reads `tsconfig.json` paths, follows `package.json` deps, indexes `*.test.ts` colocated with `*.ts`, recognizes zod schemas as contracts worth extracting).
7. **Extend `schemas/execution_plan.py::TaskStep`** with `context_excerpts: list[ContextExcerpt]` (fields: `file`, `lines`, `why`). Update `meta-prompter.md` iron law to populate these when the step references a pre-existing contract. Update `ts-dev.md`, `test-engineer.md`, `python-dev.md` process steps to consume them before re-Reading.
8. **Patch `verifier` agent + `/verify` command** to read `verify_cmd` from the active plan (or package-manager-detect: pnpm → `pnpm test`, npm → `npm test`, uv → `uv run pytest`, just → `just test`). Never hard-code `just test`.

---

*Read-only pass. No target-repo files modified. Proposals are file-level but not authored here.*
