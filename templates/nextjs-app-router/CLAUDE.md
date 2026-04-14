# Project rules (nextjs-app-router)

Scaffolded from the soup `nextjs-app-router` template. Parent `CLAUDE.md` +
`CONSTITUTION.md` iron laws apply.

## Stack

- **Framework:** Next.js 15 (App Router)
- **Runtime:** React 19 (Server Components by default)
- **Language:** TypeScript strict (`noUncheckedIndexedAccess`, `noImplicitReturns`)
- **Styling:** Tailwind 4 + shadcn-ui building blocks
- **Database:** Supabase (Postgres + Auth + RLS)
- **Unit tests:** Vitest + Testing Library (jsdom)
- **E2E tests:** Playwright (Chromium)
- **Paths alias:** `@/*` -> `./src/*`

## Layout

```
src/
  app/
    layout.tsx              Server Component root
    page.tsx                Server Component home
    globals.css             Tailwind entry
    api/health/route.ts     Route Handler (force-static)
  middleware.ts             Routing Middleware stub
  lib/supabase/
    client.ts               "use client" browser client (anon key)
    server.ts               Server Component / Route Handler client
  __tests__/
    setup.ts                jest-dom matchers
    smoke.test.ts           unit test baseline
e2e/
  health.spec.ts            Playwright smoke
supabase/
  config.toml               CLI config
  migrations/0001_init.sql  baseline schema + RLS policies
playwright.config.ts
vitest.config.ts
next.config.ts
tsconfig.json
```

## Rules for agents

1. **Server Components by default.** Only add `"use client"` when a file
   uses hooks, event handlers, browser APIs, or Context providers. Keep
   the client boundary thin — extract a small island; do not mark entire
   pages or layouts as client.
2. **Route Handlers (`app/**/route.ts`) run Node by default.** Mark
   `export const runtime = "edge"` only when the handler needs the edge.
3. **Server Actions (`"use server"`) are the default for mutations.**
   Use Route Handlers for things that need HTTP semantics (third-party
   webhooks, non-browser clients, public JSON APIs).
4. **Auth + DB via `@supabase/ssr`.** Use `lib/supabase/server.ts` from
   Server Components / Route Handlers / Server Actions;
   `lib/supabase/client.ts` from `"use client"` components. Never import
   the server module into a client-tagged file (the linter will catch it;
   code review must still check).
5. **Never ship `SUPABASE_SERVICE_ROLE_KEY` to the client.** It bypasses
   RLS. Use it in non-request admin contexts (background jobs, scripts)
   only. Public env vars use `NEXT_PUBLIC_` prefix; server-only env vars
   do not.
6. **Every table has RLS.** Default-deny, then add explicit policies
   per role. Test both the allowed and the forbidden paths. See
   `rules/supabase/client-and-migrations.md`.
7. **Migrations are immutable.** `supabase migration new <slug>` creates
   a new file; never edit an applied migration. Use expand/contract for
   schema changes. Regenerate DB types after every schema change:
   `just gen-types` -> `src/types/database.ts` (commit it).
8. **No raw SQL from app code.** Use the Supabase client (typed via
   `Database` generic) or call a Postgres function. Raw SQL belongs in
   migrations only.
9. **Strict TypeScript.** No `any`. No `@ts-ignore`. No
   `@ts-expect-error` without a linked issue. Prefer `unknown` +
   narrowing. The `noUncheckedIndexedAccess` rule is on; handle
   `undefined` from `array[i]` and `map.get(key)`.
10. **Every route/handler/component is tested.** Vitest for unit,
    Playwright for route behavior. E2E is mandatory when `searchParams`,
    redirects, or auth cookies are involved — unit tests cannot cover
    those reliably.
11. **`searchParams` is a Promise in Next 15+.** Server Component page
    signatures: `{ searchParams: Promise<Record<string, string | string[]>> }`.
    `await` it at the top of the component.
12. **Metadata lives in `layout.tsx` / `page.tsx`** via `export const
    metadata`. Dynamic metadata uses `generateMetadata`. Do not use
    `<Head>` — that's Pages Router.
13. **No inline network fetches that bypass auth.** Every `fetch` from
    a Server Component either hits a typed helper or uses the Supabase
    client. Third-party calls go through `lib/` with explicit host
    checks.
14. **Middleware is tight.** Keep it under ~50ms p50. Slow middleware
    blocks every matched request.

## Local dev

```bash
just init        # npm install
just dev         # next dev on :3000
just test        # vitest run
just test-e2e    # playwright test (boots next dev via webServer)
just lint
just typecheck
just build
```

Supabase:

```bash
supabase start
just migrate add_foo          # creates supabase/migrations/<ts>_add_foo.sql
# edit the file, then:
just migrate-up               # supabase db push
just gen-types                # regenerate src/types/database.ts
```

## What NOT to do

- Do not mix Pages Router (`pages/`) and App Router (`app/`) unless you
  know why. This template is App Router only.
- Do not read from `process.env.SUPABASE_SERVICE_ROLE_KEY` outside of
  server-only modules. Add a `server-only` import to any file that must
  not accidentally be bundled into client code.
- Do not bypass RLS "just for this one script." Write the script as a
  proper admin module in `scripts/` with its own client.
- Do not edit `next-env.d.ts` — Next regenerates it.
