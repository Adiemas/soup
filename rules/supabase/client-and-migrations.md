# Supabase — client split + migrations + RLS

Rules for any project using Supabase (Postgres + Auth + RLS + Storage).
Linked from `rules/global/security.md` (secret handling) and
`templates/nextjs-app-router/CLAUDE.md`.

## 1. Anon key vs service role — never mix

| Key | Where | RLS applies? | Env var |
|---|---|---|---|
| **Anon** (`NEXT_PUBLIC_SUPABASE_ANON_KEY`) | Browser + Server Components via `@supabase/ssr` | **Yes** | `NEXT_PUBLIC_*` — public by design |
| **Service role** (`SUPABASE_SERVICE_ROLE_KEY`) | Server-only admin scripts / cron | **Bypassed** | **Server-only.** Never `NEXT_PUBLIC_*` |

Rules:

1. The browser bundle MUST NEVER receive the service-role key. Add a
   top-level `import "server-only";` to any module that reads
   `SUPABASE_SERVICE_ROLE_KEY` so accidental client imports fail the
   build.
2. Service-role clients only live in admin-surface code: one-off
   scripts, scheduled jobs, migrations, webhook handlers that are
   authenticated by a shared-secret header (not cookies).
3. The anon key is public. RLS is the only thing standing between it
   and your data. Default-deny every table (see §3).

## 2. `@supabase/ssr` cookie pattern (App Router)

Canonical server-side client for Server Components / Route Handlers /
Server Actions:

```ts
// src/lib/supabase/server.ts
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function createClient() {
  const cookieStore = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            );
          } catch {
            // Ignored: setAll throws when called from a Server Component;
            // middleware is responsible for refreshing sessions.
          }
        },
      },
    }
  );
}
```

Browser client (called from `"use client"` components):

```ts
// src/lib/supabase/client.ts
"use client";
import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
```

### Middleware for session refresh

When using authenticated routes, add a middleware that refreshes the
user session on every request that reaches a protected path:

```ts
// src/middleware.ts
import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";

export async function middleware(request) {
  let response = NextResponse.next({ request });
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return request.cookies.getAll(); },
        setAll(cookies) {
          cookies.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookies.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options)
          );
        },
      },
    }
  );
  await supabase.auth.getUser();
  return response;
}
```

Do NOT skip `getUser()` — it is what forces the token to refresh.
`getSession()` from the browser client is cached and will not refresh.

## 3. RLS checklist (every table)

1. `alter table public.<name> enable row level security;` on every
   table in the `public` schema. New tables without RLS are a leak.
2. Default-deny: no policies = no access (for anon / authenticated).
   Only the service role bypasses.
3. Write explicit policies per operation (`select`, `insert`, `update`,
   `delete`) and per role (`anon`, `authenticated`, custom).
4. `with check` on `insert` and `update` — clause runs on the new row.
   `using` runs on the existing row (matters for update/delete).
5. Test BOTH paths: a user who should succeed AND a user who should be
   denied. A policy test that only checks the allowed case has not been
   tested.
6. Index foreign-key columns and any column used in a policy's
   `using`/`with check` clause — otherwise RLS turns every query into a
   sequential scan.

Example:

```sql
alter table public.items enable row level security;

create policy "items_select_own" on public.items
  for select to authenticated
  using (user_id = auth.uid());

create policy "items_insert_own" on public.items
  for insert to authenticated
  with check (user_id = auth.uid());

create index if not exists items_user_id_idx on public.items (user_id);
```

## 4. Migrations — immutable; expand/contract

1. `supabase migration new <slug>` creates a new timestamped SQL file
   under `supabase/migrations/`. NEVER edit a migration that has been
   applied to any environment (including staging). Once shipped,
   migrations are append-only.
2. To change schema shape, use **expand/contract**:
   - Expand: add the new column/table/index, backfill, switch readers
     to the new column in application code. Ship.
   - Contract: drop the old column/table. Ship.
3. Additive changes (new table, new column with default, new index) are
   low risk. Destructive changes (drop column, drop table, rename) need
   an expand phase first.
4. `create index concurrently` for large tables (Postgres doesn't lock
   the table). Outside a migration transaction — configure your tooling
   to run these separately.
5. Never `drop / recreate` a migration in place to "reset." That breaks
   every collaborator who already applied the prior version. Write a
   new migration that forward-fixes the schema.

## 5. Generated types — commit them

After every schema change:

```bash
supabase gen types typescript --local > src/types/database.ts
git add src/types/database.ts
```

1. Commit the generated file. Engineers opening a PR should see the
   type change next to the migration — the diff reviews both.
2. Wire the `Database` type into the client:
   ```ts
   import type { Database } from "@/types/database";
   const supabase = createServerClient<Database>(url, anon, { ... });
   ```
3. CI: run `supabase gen types ... | diff - src/types/database.ts` and
   fail if there's drift. Regeneration must be intentional.

## 6. Extension enablement

Enable in a migration, not via the dashboard (migrations must be
reproducible on every environment):

```sql
create extension if not exists "pgcrypto";    -- gen_random_uuid()
create extension if not exists "vector";      -- pgvector for embeddings
create extension if not exists "pg_stat_statements";
```

For pgvector specifically:

```sql
create table public.chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  embedding vector(1536) not null,
  content text not null
);

-- HNSW is the modern default; tune m/ef_construction per dataset.
create index on public.chunks
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);
```

Indexes on vector columns only go on populated tables (sparse indexes
perform badly). Backfill, then index, then flip readers.

## 7. When NOT to use Supabase

- Write-heavy workloads where RLS per-query overhead matters (measure;
  usually fine, but not always).
- Schemas that need Postgres features Supabase pins away from (older
  version, custom extensions not on the allow-list).
- Apps that need direct low-level Postgres connections from short-lived
  Lambda-style runtimes — pgbouncer transaction-mode compatibility
  varies by driver.
