# your-app -- Next.js (App Router) + Supabase

Scaffolded from the soup `nextjs-app-router` template.

## Quick start

```bash
just init
just dev       # http://localhost:3000
```

## Supabase

```bash
supabase start                # boots local postgres + auth + studio
just migrate add_users        # new migration
just migrate-up               # supabase db push
just gen-types                # regenerate src/types/database.ts
```

## Tests

```bash
just test                     # vitest run (unit)
just test-e2e                 # playwright (e2e, boots next dev)
```

## Build

```bash
just build                    # .next/ production bundle
docker build -t your-app:latest .
```

## Layout

See `CLAUDE.md` for the agent contract and Server Component rules.
