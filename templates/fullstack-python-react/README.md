# fullstack-python-react

Scaffolded from the soup `fullstack-python-react` template — FastAPI backend +
React frontend + Postgres, composed via docker-compose behind nginx.

## Quick start

```bash
just up
open http://localhost:8080            # SPA
curl http://localhost:8080/api/health # backend via nginx proxy
```

## Tests

```bash
just test     # pytest + vitest
```

## Layout and rules

See `CLAUDE.md`.

## Ports

| Service | Host port | Container port |
|---|---|---|
| web (nginx) | 8080 | 80 |
| api (uvicorn) | internal | 8000 |
| db (postgres) | internal | 5432 |

Dev overrides: `VITE_API_TARGET=http://localhost:8000 npm run dev`.
