# Soup — Docker compose stack

Local dev stack for the soup framework. Two services:

- `postgres` — Postgres 16 + pgvector, bound to `127.0.0.1:5432` only.
- `soup-dev` — dev container with python 3.12, just, gh, docker CLI,
  psql, az. Runs as the non-root `soup` user (uid 1000, see
  `Dockerfile.dev`).

```sh
# From the repo root:
docker compose -f docker/docker-compose.yml up -d
```

## Security posture

The compose file is hardened to avoid the common "dev container that owns
the host" pattern that the cycle-1 critic review flagged as CRITICAL:

1. **No host docker socket.** The `/var/run/docker.sock` bind mount has
   been removed. Mounting the host docker socket into a container that
   executes agent-authored code is a container-escape primitive: a
   subagent can run `docker run --privileged -v /:/host ubuntu chroot
   /host` and own the host filesystem. This is not theoretical.

2. **Non-root container user.** The dev container runs as `soup`
   (uid 1000), not root. Verified in `Dockerfile.dev` (`USER ${USERNAME}`).

3. **Loopback-bound Postgres.** The Postgres port is published as
   `127.0.0.1:5432` rather than `:5432`, so the dev DB is never reachable
   from other machines on the network.

4. **Explicit credentials.** `POSTGRES_PASSWORD` should be set in your
   `.env`. The compose file still carries a `:-soup` fallback so
   `docker compose up` does not hard-error, but you MUST override it
   before pointing the stack at anything non-local.

## Docker-in-docker for local dev (opt-in only)

If you genuinely need to run `docker` commands from inside the dev
container (e.g. to build a child image for a mock app), create a
**separate** override file on your own machine and invoke compose with
both files. Do not commit the override.

`docker/docker-compose.dind.override.yml`:

```yaml
# SECURITY: this file mounts the host docker socket into soup-dev.
# Only use on a single-user local workstation. NEVER use this file on
# a shared machine, a CI runner, or any host that executes agent code
# you did not write yourself.
services:
  soup-dev:
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

Then run:

```sh
docker compose \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dind.override.yml \
  up -d
```

### Safer alternatives

Prefer these over mounting the host socket:

- **Sibling docker service** (`docker:dind`) with its own TLS cert —
  the dev container talks to a network endpoint, not the host.
- **Sysbox** or **rootless docker** inside the dev container.
- **Host-side tooling** — run `docker build` on the host, not inside
  the dev container. The dev container still has the `docker` CLI for
  client use against a remote engine (`DOCKER_HOST`).

## Database initialization

`postgres-init.sql` is mounted read-only at
`/docker-entrypoint-initdb.d/00-postgres-init.sql`. It runs **once** on
a fresh volume. The `DO $$` block is idempotent for safe re-runs, but
if you change the role password you must either:

1. Recreate the volume (`docker compose down -v`), or
2. Run `ALTER ROLE soup WITH PASSWORD '...'` manually.

## Resetting the stack

```sh
docker compose -f docker/docker-compose.yml down -v
```

`-v` drops the `soup-pg-data` volume — everything is regenerated on the
next `up`.
