# Project rules (python-fastapi-postgres)

This project was scaffolded from the soup `python-fastapi-postgres` template.
The parent repo `CLAUDE.md` + `CONSTITUTION.md` iron laws apply here. Additional
project-specific rules:

## Stack

- **Runtime:** Python 3.12, FastAPI, uvicorn
- **DB:** Postgres 16, `psycopg` (async) + `psycopg_pool`
- **Tests:** pytest + httpx
- **Lint:** ruff + mypy strict

## Layout

```
app/
  main.py       FastAPI app + lifespan
  db.py         AsyncConnectionPool wrapper
  models.py     Pydantic request/response models
migrations/
  0001_init.up.sql / 0001_init.down.sql
tests/
  test_health.py
```

## Rules for agents

1. **New endpoints live in `app/`**; route registration happens in `main.py`.
2. **DB access goes through `Database`** (see `app/db.py`). No raw connections.
3. **Every DB-touching endpoint has a test** using the `_StubDB` pattern in `tests/test_health.py`.
4. **Schema changes require a migration pair** (`NNNN_name.up.sql` + `NNNN_name.down.sql`).
   Increment the version prefix, never edit applied migrations. Author via the `sql-specialist` agent.
5. **Pydantic models are frozen contracts** for the API surface. Additive-only changes without a version bump.
6. **No secrets in code.** Read from env. `.env.example` documents what is required.
7. **`ruff check` and `mypy --strict` must pass** before any commit.

## Local dev

```bash
just init          # install deps
just up            # docker compose: postgres + api
just test          # run pytest
just migrate-up    # apply migrations
```
