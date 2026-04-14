# Dogfooding soup against Middle-Earth-App (MESBG Data Hub)

**Date:** 2026-04-14
**Target:** `C:\Users\ethan\Personal-Projects\Middle-Earth-App`
**Soup:** `C:\Users\ethan\AIEngineering\soup`
**Mode:** read-only propose-only dry run.

## Target snapshot

**Stack:** Next.js 16 (App Router) + React 19 + TypeScript 5 (strict) + Tailwind 4 + shadcn/ui + `@base-ui/react`. Supabase (`@supabase/supabase-js` 2.x) with pgvector; migrations in `supabase/migrations/` (SQL). Vercel AI SDK 6 with Google Gemini. Firecrawl + Tavily for scraping. `npm` (lockfile present), Vitest 4 (jsdom) for unit, Playwright 1.59 for e2e, ESLint 9 flat config via `eslint-config-next`.

**Notable dirs/files:**
- `src/app/` — App Router: `layout.tsx`, `page.tsx`, `api/` (chat, explorer, ingest, pipeline, scrape), `explorer/`, `pipeline/`, `rules/`, a stray `browse-client.tsx`.
- `src/lib/{ai,rag,scraper,supabase}/` — business logic. `supabase/{client.ts, server.ts, queries.ts}` — split anon-key client vs service-role server helper (no `@supabase/ssr` cookie pattern).
- `src/components/ui/` — shadcn, plus colocated `__tests__/`.
- `e2e/{chat,explorer,navigation,pipeline,smoke}.spec.ts` + `e2e/fixtures/base.ts`. Playwright `webServer` runs `npm run dev`.
- `supabase/migrations/001..003` — raw SQL; migration 003 drops/recreates (early-dev reset).
- `.mcp.json` — single Supabase HTTP MCP pinned to `project_ref`.
- `.vercel/` exists (linked project). `.env.local` + `.env.local.example`.

**Pre-existing agent setup:**
- `CLAUDE.md` short and factual; names spec path `docs/superpowers/specs/...`.
- `AGENTS.md` is a two-liner warning ("this is NOT the Next.js you know — read `node_modules/next/dist/docs/` first").
- `.superpowers/brainstorm/1228-1775226625/` — HTML brainstorm artifacts (layouts, frontend approaches).
- `agentic-dev-framework/` — 286-file knowledge base (research phases 1-4 + handbook + templates for CLAUDE.md/skills/hooks/schemas/agent-harnesses/project-scaffolds). **This sibling repo already contains much of what soup aims to be.** It's a strong, independent reference rather than a consumer of soup.
- `test-results/.last-run.json` — `{status: "passed", failedTests: []}`, no active failures.

## Soup readiness for this stack

| Concern | Status | Evidence |
|---|---|---|
| Next.js App Router template | **Missing** | `templates/` has only `react-ts-vite` and `fullstack-python-react`; no Next.js scaffold, middleware, or `app/` globs. |
| Next.js agent/rules | **Partial** | `rules/react/coding-standards.md` is Vite-centric ("`vite.config.ts`", "`import.meta.env.VITE_*`"), explicitly calls "Vite build". `.claude/agents/react-dev.md` declares stack "React 18+, Vite, TS". No Server Components, Server Actions, or metadata-routes guidance. |
| React 19 | **Gap** | Rules target React 18+; no mention of React 19 hooks (`use`, Actions, `useOptimistic`) which this repo depends on. |
| Supabase guidance | **Missing** | `rules/postgres/migrations.md` is generic Postgres; no Supabase client split (anon vs service role), no `@supabase/ssr` cookies, no RLS, no `supabase gen types typescript`. |
| Vercel deploy rules | **Missing** | No `rules/vercel/*`, no `vercel.ts`/`vercel.json`, no preview-URL or `vercel env pull` guidance. (Repo *is* Vercel-linked.) |
| Playwright patterns | **Thin** | `rules/react/coding-standards.md` §9 just says "Playwright with a `beforeEach` that seeds an isolated dataset." No fixtures template, no `webServer` idiom, no CI workers/retries wisdom. |
| pnpm vs npm | **Gap** | `cli_wrappers/` has no package-manager wrapper at all (no `npm.py` / `pnpm.py`). TS standards §11 says "prefer pnpm for monorepos" then verify commands in agents assume `npm`. Target repo uses `npm` exclusively; this happens to align but is accidental. |
| MCP config examples | **Missing** | Soup has no `rules/mcp/*` or template `.mcp.json`. Target repo ships a 148-byte HTTP MCP pinned to `project_ref`; nothing in soup documents that pattern. |
| Systematic debugging | **Strong** | `.claude/skills/systematic-debugging/SKILL.md` 4-phase + 3-strike rule transfers cleanly. |
| Spec/plan/tasks flow | **Strong** | `/specify → /clarify → /plan → /tasks → /implement → /verify` pipeline is stack-agnostic and works here. |

## Scenarios

### Scenario A — Feature: "Add a filter on /characters by faction (elf, dwarf, hobbit, men, orc, other)"

**/specify** works fine — EARS statements like "The system shall display only characters matching the selected faction when the user clicks a faction chip on /characters; the system shall deep-link the filter via `?faction=elf` when the URL changes; the system shall render an 'All' pill that clears the filter." Spec lands at `specs/characters-faction-filter-2026-04-14.md`. Clarify loop catches ambiguity: is `faction` derived from `army_type` (Good/Evil) or a new column? (Checking migration 003: `units.army_type` exists but `units.faction` does not — open question for `/clarify`.)

**/plan** is where soup leaks. `architect` will choose a stack, but it only knows "Streck stack (Python/.NET/React/TS/Postgres/Docker)" per `/plan.md` line 18. Next.js App Router isn't named. `plan-writer` is told `files_allowed` should be narrow; it will guess at `src/components/characters/*.tsx`, likely missing that:
- The filter belongs in a **Server Component** (`src/app/characters/page.tsx`) reading `searchParams`, not in a client hook.
- A `'use client'` child handles chip interactivity and `router.push` with `searchParams`.
- The Supabase query must run on the server (service role) OR via anon with RLS — soup has no guidance here.

**/tasks** JSON will emit tasks like "T3 implement filter component" with `verify_cmd: vitest run src/components/characters/FactionFilter.test.tsx` — good. But it won't know to emit a Playwright e2e task; `test-engineer` chooses frameworks by extension and will default to Vitest/RTL for `.tsx`. No rule tells it "a new route/searchParams behavior gets an `e2e/*.spec.ts`".

**/implement** with `react-dev` agent: agent card lists Vite + RTL + Playwright — will run `vitest run` fine, but `tsc --noEmit` is fine, and `eslint` works (flat config is supported). It will NOT know `next dev` is the command or that `.next/types/**/*.ts` must be in `include`. No `next build` pre-check.

**/verify**: `verify_cmd` strings are runnable, but `verifier.md` auto-runs `just test` if present — **this repo has no justfile**. Verifier must fall back to declared commands. `pnpm test:e2e` doesn't exist here; it's `npm run test:e2e`, and Playwright will spawn `npm run dev` via `webServer` — fine, but nothing tells soup "ensure port 3000 is free first."

**Breaks:** plan targets wrong layer (client instead of Server Component); e2e task missing; no `app/` glob pattern.

### Scenario B — Debug: "Playwright test flakes on CI because of race on hydration" (plausible; `test-results/` is currently green)

`.superpowers/systematic-debugging` applies cleanly.

- **Phase 1 Investigate.** Reproduce: `CI=1 npm run test:e2e -- --project=chromium`. Capture traces (`trace: 'on-first-retry'` is set). Note `workers: isCI ? 1 : undefined` and `retries: 2`. Soup advises recording commit SHA, env, exact flake rate.
- **Phase 2 Pattern.** Class: async/hydration race. Search `e2e/` for `page.goto` followed immediately by `page.click` without `waitFor`. shadcn `cmdk` popovers hydrate lazily — assertion on an element rendered by a `'use client'` island before hydration completes is the classic culprit.
- **Phase 3 Hypothesis.** "`explorer.spec.ts` clicks a faction chip inside a `'use client'` Command palette before React attaches its listener; the click is swallowed." Minimal distinguishing test: pre-click, assert `await expect(chip).toBeEnabled()` and `await page.waitForFunction(() => (window as any).__NEXT_HYDRATED === true)` (or use `page.waitForLoadState('networkidle')` as proxy).
- **Phase 4 Fix.** Replace `click()` with `locator.click({ trial: true })` followed by real click, or gate on a data attribute (`data-hydrated="true"`) set by a top-level client component. Commit with hypothesis in body.

**Soup gap surfaced:** `systematic-debugging` says nothing about RSC hydration, `'use client'` boundaries, or Next.js-specific flake patterns. A Next.js-flavored debugging addendum would land well.

### Scenario C — Docs + refactor: "Document the Supabase migration workflow for new contributors"

`doc-writer` (haiku, scope-limited) is the right agent. Its iron law ("scope = recently modified code only") is actually a **bad fit** here — the request is net-new onboarding documentation, not a reflection of a diff. Soup would need to either loosen `doc-writer` or introduce a sibling `onboarding-docs` agent.

Walking it anyway:
1. Read `CLAUDE.md` + `supabase/migrations/*.sql` + `src/lib/supabase/{client,server,queries}.ts` + `scripts/` (if DB seeding lives there) + `.env.local.example`.
2. Identify doc location. `doc-writer.md` catalog has no "migrations runbook" row. Closest match is `docs/runbooks/<op>.md` — good, land it at `docs/runbooks/supabase-migrations.md`.
3. Surgical additions to cover: local Supabase start (`supabase start`), create-migration (`supabase migration new <slug>`), apply (`supabase db push`), type regen (`supabase gen types typescript --local > src/types/database.ts`), preview/prod promotion, rollback strategy given mig003 uses destructive drops. Cross-ref `CLAUDE.md` ("Supabase migrations in `supabase/migrations/`") and `.env.local.example`.

**Soup gap:** `rules/` has no `rules/supabase/migrations.md` to *guide* the doc-writer. `rules/postgres/migrations.md` exists but is generic and doesn't cover the Supabase CLI, RLS policies, pgvector embeddings, or `supabase gen types` — all present in this repo. Without that rule, `doc-writer` will invent or omit.

## Concrete soup gaps surfaced

1. **No Next.js template.** `templates/nextjs-app-router/` is missing. Needs: `src/app/` globs, `middleware.ts`, `next.config.ts`, Route Handlers vs Server Actions convention, metadata files (`robots.ts`, `sitemap.ts`, `opengraph-image.tsx`), `'use client'`/`'use server'` boundary rules.
2. **No Supabase rule pack.** Needs: anon-vs-service-role client split (matches target's `client.ts`/`server.ts`), `@supabase/ssr` cookie pattern for App Router, RLS policy authoring, `supabase gen types typescript` workflow, migration conventions (non-destructive, numbered, idempotent), pgvector index patterns.
3. **No Vercel deploy rules.** Needs: `vercel env pull`, preview URLs, linked-project safety (`.vercel/project.json`), function runtime selection, `vercel.json` rewrites.
4. **Playwright patterns shallow.** Target has `e2e/fixtures/base.ts`; soup has no fixture template, no `webServer` idiom doc, no data-seeding-per-worker recipe, no parallel-isolation guidance beyond one sentence.
5. **`cli_wrappers/` has no Node/npm/pnpm wrapper.** Current wrappers: `ado, docker, dotnet, gh, git, psql`. For any JS/TS stack, agents shell out raw to `npm`/`pnpm` without the structured `{status, data}` contract the Python wrappers provide.
6. **MCP config pattern undocumented.** Soup ships zero `.mcp.json` examples. Target uses HTTP-type MCP with a `project_ref` query param — worth a `templates/mcp/` directory with examples (HTTP, stdio, sse).
7. **`.superpowers/brainstorm/` HTML artifacts** in the target are interesting — they're renderable brainstorm outputs (layouts + frontend-approaches). Soup's `brainstorming` skill outputs only markdown; an optional HTML-deck rendering step would be a real ergonomic win.
8. **`agentic-dev-framework/` is a 286-file parallel knowledge base.** Its `templates/{claude-md, skills, hooks, schemas, agent-harnesses, project-scaffolds}/` directly overlap with soup's `templates/` and `.claude/skills/`. Worth a one-time sync pass to pull their skill templates and schema designs into soup's `rules/` and `templates/`. Specifically the `project-scaffolds/` folder likely has a Next.js scaffold soup is missing.
9. **React agent is Vite-locked.** `.claude/agents/react-dev.md` needs a Next.js App Router mode (or fork into `nextjs-dev.md`).
10. **React rules are React-18-only.** No guidance on React 19 Actions / `use()` / `useOptimistic` / async components.

## Ergonomic wins

Things soup WOULD do well on this app out of the box:

- `/specify` + EARS requirements fit Phase-1 scope docs perfectly (target already stores a spec at `docs/superpowers/specs/...`).
- `systematic-debugging` 4-phase + 3-strike rule maps 1:1 onto Playwright flake hunts.
- `tdd` skill + `test-engineer` agent's "must fail for the right reason" rule is exactly what this codebase's vitest-colocated pattern expects.
- `verification-before-completion` drops straight in — verify commands are `npm run test:run`, `npm run test:e2e`, `npm run build`.
- `architect` + `plan-writer` generate the file-map skeleton that `plan-writer.md` requires; the markdown-first (JSON later via `/tasks`) split plays well with human PR review.
- TypeScript coding standards (strict config, zod at boundary, branded IDs, discriminated unions, exhaustiveness, no `any`) transfer unchanged and would immediately uplift this codebase.
- `code-reviewer` + `security-scanner` + `verifier` parallel fan-out via `/verify` needs no changes to run here.

## Proposed soup additions

Prioritized 1-8, each is a concrete file + one-sentence purpose.

1. **`templates/nextjs-app-router/`** — scaffold for App Router projects: `src/app/{layout,page}.tsx`, `middleware.ts`, `next.config.ts`, `eslint.config.mjs` using `eslint-config-next`, `playwright.config.ts` with `webServer`, `vitest.config.ts` with jsdom, CLAUDE.md citing React 19 + Server Components.
2. **`rules/nextjs/app-router.md`** — Server Component / `'use client'` / `'use server'` boundary rules, searchParams as async Promise (Next 15+), Route Handlers vs Server Actions, metadata file conventions, `dynamic`/`revalidate` exports, caching tiers.
3. **`rules/supabase/client-and-migrations.md`** — anon vs service-role split, `@supabase/ssr` cookie client for App Router, RLS authoring checklist, `supabase migration new/up/reset` workflow, `supabase gen types typescript` as a pinned command, pgvector index guidance.
4. **`rules/vercel/deploy.md`** — `vercel link`, `vercel env pull` into `.env.local`, preview URL semantics, `vercel.json` rewrites, function runtime selection, treating `.vercel/project.json` as committed-vs-local.
5. **`rules/mcp/config.md`** + **`templates/mcp/{http,stdio,sse}.json`** — canonical `.mcp.json` examples including the HTTP-with-project-ref pattern this target uses.
6. **`cli_wrappers/npm.py`** (and/or `pnpm.py`) — JSON-emitting wrapper matching the `{status, data}` contract of existing wrappers; subcommands: `install`, `run <script>`, `audit`, `ci`, `test`, `build`. Fixes agents shelling out raw.
7. **`.claude/agents/nextjs-dev.md`** (fork of `react-dev.md`) — Next.js + Supabase + Vercel specialist; knows App Router conventions, picks Server Component by default, writes Playwright e2e alongside unit tests for any new route.
8. **`.claude/skills/debugging-hydration-and-rsc/SKILL.md`** — Next.js-flavored addendum to `systematic-debugging`: hydration race patterns, `'use client'` boundary bugs, `searchParams` async changes in Next 15+, Playwright waits that work under RSC streaming.

Additional cleanup (not in top 8): sync in relevant pieces from `Middle-Earth-App/agentic-dev-framework/templates/project-scaffolds/` if a Next.js scaffold is there; add `React 19 Actions / use() / useOptimistic` section to `rules/react/coding-standards.md`.
