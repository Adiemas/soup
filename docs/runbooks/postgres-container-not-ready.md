# docker-compose Postgres — container not ready on app startup

## Symptom

One of the following, immediately after `docker compose up`:

```
psycopg.OperationalError: connection to server at "postgres" (172.x.y.z), port 5432 failed: Connection refused
```

```
FATAL: the database system is starting up
```

```
sqlalchemy.exc.DBAPIError: database is not ready
```

The app container starts, tries to connect, fails, exits, and
docker-compose restarts it — sometimes looping until you stop it or
Postgres finally warms up.

## Cause

`depends_on` in docker-compose only guarantees **container start
order**, not **service readiness**. The Postgres container can be
"started" (process launched, port open for listening), but the
initdb/bootstrap phase takes several seconds during which connections
are rejected. The app container races past `depends_on` and tries to
connect before the server is actually accepting queries.

This race is particularly bad in CI where cold-start disk latency
pushes initdb to 10+ seconds.

## Fix

Use the **`depends_on` + `healthcheck` + `condition: service_healthy`**
pattern.

### docker-compose snippet

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-app}
      POSTGRES_USER: ${POSTGRES_USER:-app}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-app}
    healthcheck:
      # pg_isready respects auth; test from inside the container.
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-app} -d ${POSTGRES_DB:-app}"]
      interval: 2s
      timeout: 3s
      retries: 30
      start_period: 10s

  app:
    build: .
    depends_on:
      postgres:
        condition: service_healthy   # NOT `- postgres`
```

### Why these numbers

- `interval: 2s` — fast enough to unblock the dependent service
  within ~2s of readiness on a warm boot.
- `retries: 30` × `interval: 2s` = 60 s total wait ceiling, which is
  comfortable for cold-boot initdb on CI disk IO.
- `start_period: 10s` — grace window where failed probes do not count
  towards `retries`; covers the typical initdb bootstrap time.

### App-side belt-and-braces

Even with `condition: service_healthy`, your app should retry
connections on startup for the first ~30 s — network hiccups still
happen, and a Postgres restart mid-run should not crash the service:

```python
# Python example — mirror the shape in your stack.
import time
import psycopg

for attempt in range(15):
    try:
        conn = psycopg.connect(DSN)
        break
    except psycopg.OperationalError:
        if attempt == 14:
            raise
        time.sleep(2)
```

## What NOT to do

- **Do not add `sleep 30` before the app's entrypoint.** That ships
  fixed latency into production and still races on slow CI.
- **Do not remove `depends_on`.** You still need the start-order
  guarantee; the healthcheck just tightens what "depends" means.

## Related

- `docker/docker-compose.yml` — reference compose file.
- `rules/postgres/migrations.md` — Alembic + Postgres conventions.
- `.claude/skills/systematic-debugging/SKILL.md` — if a flake persists
  after applying this fix, work through the 4-phase process rather
  than adding more sleeps.
