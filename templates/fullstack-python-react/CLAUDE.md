# Project rules (fullstack-python-react)

Scaffolded from the soup `fullstack-python-react` template. Parent
`CLAUDE.md` + `CONSTITUTION.md` iron laws apply. This project composes a
Python FastAPI backend with a React TypeScript frontend.

## Stack

- **Backend:** Python 3.12, FastAPI, psycopg 3
- **Frontend:** React 18, TypeScript strict, Vite 5
- **DB:** Postgres 16
- **Prod:** nginx serves the frontend and proxies `/api/*` to the `api` service

## Layout

```
backend/                 FastAPI service (port 8000)
  app/main.py            /health, /greet/{name}
  migrations/            SQL migration pairs
  tests/test_api.py
  Dockerfile
frontend/                React SPA (port 80 behind nginx)
  src/App.tsx            consumes /api/health + /api/greet
  nginx.conf             /api → api:8000
  Dockerfile
docker-compose.yml       db + api + web
justfile                 top-level recipes
```

## Rules for agents

1. **Contracts first.** When adding an endpoint, update the backend model and
   the frontend fetch together; write tests in **both** halves before merging.
2. **Backend returns Pydantic models.** Frontend parses to TS `interface`s
   that mirror them. Breaking changes require a version bump.
3. **All frontend network calls go through `/api/*`.** The proxy (Vite dev,
   nginx prod) takes care of routing. Never hardcode backend hosts.
4. **Tests mock at the edges.**
   - Backend tests: monkeypatch `_db_ping` (no live DB).
   - Frontend tests: `vi.stubGlobal("fetch", ...)`.
5. **Schema changes:** add a migration pair in `backend/migrations/`.
6. **`docker compose up` must bring the whole stack up.** Break it, you fix it.
7. **CLAUDE.md in each half** (backend/, frontend/) stays empty by default —
   project-level rules live here.

## Local dev

Two terminals (recommended):

```bash
# term 1
just dev-backend        # :8000
# term 2
just dev-frontend       # :5173 (proxies /api → :8000)
```

Full stack in docker:

```bash
just up
curl http://localhost:8080/api/health
```
