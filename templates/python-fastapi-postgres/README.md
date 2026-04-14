# your-api — FastAPI + Postgres

Scaffolded from the soup `python-fastapi-postgres` template.

## Quick start

```bash
just init     # install deps
just up       # docker compose: postgres + api on :8000
curl http://localhost:8000/health
```

Expected:

```json
{"status":"ok","db":true}
```

## Tests

```bash
just test
```

The health test stubs the DB pool, so it runs without a live Postgres.

## Migrations

Forward/back pairs in `migrations/`. Apply via:

```bash
just migrate-up     # needs POSTGRES_* env vars or POSTGRES_DSN
just migrate-down
```

## Env

See `.env.example` (or rely on docker-compose defaults for local dev).

## Layout

See `CLAUDE.md` for the agent contract.
