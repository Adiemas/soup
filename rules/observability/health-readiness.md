# Health, readiness, and version endpoints

Every service exposes three orthogonal endpoints. Conflating them
into one `/health` is a recurring outage pattern — a reachable-but-
bootstrapping process returns `ok` and the load balancer sends it
traffic it cannot serve.

| Endpoint | Semantics | Check depth | Deps? |
|---|---|---|---|
| `/health` | Process is alive | Trivial: returns 200 if the process can respond | None |
| `/ready` | Deps reachable, warm-up done | Ping DB, cache, critical downstream APIs | Yes |
| `/version` | Build identity | Static: returns commit SHA + build timestamp + env | None |

## `/health` contract

- Returns 200 with `{"status": "ok"}`. No DB round-trip. No external
  call.
- Purpose: LB liveness probe. If the process is deadlocked, this
  returns nothing; the LB evicts. If garbage-collecting under load,
  this returns late but 200.
- Never fails on dependency issues. A dep problem surfaces via
  `/ready`, not here.

```json
{"status": "ok"}
```

## `/ready` contract

- Returns 200 with a per-dep breakdown when every dep is reachable.
- Returns 503 with the same shape but `status: "degraded"` when any
  required dep is unreachable.
- Purpose: K8s readiness probe + load-balancer rolling-deploy gate.
- Timeouts: every dep check caps at 1s. The overall handler caps at
  3s via a `timeout` budget. Never hang the response.

```json
{
  "status": "ready",
  "checks": {
    "database": {"ok": true, "latency_ms": 4},
    "cache":    {"ok": true, "latency_ms": 1},
    "downstream_api": {"ok": true, "latency_ms": 42}
  }
}
```

## `/version` contract

- Returns 200 with identity fields. No dep calls; pure string
  lookups.
- Fields: `git_sha`, `build_time`, `env`, optionally `service`.
- `git_sha` is set by the deploy pipeline at build time via an env
  var (`GIT_SHA`, `VERCEL_GIT_COMMIT_SHA`, `GITHUB_SHA`). Fall back
  to `"dev"` if unset.

```json
{
  "service": "your-api",
  "git_sha": "9f2c1a7",
  "build_time": "2026-04-14T10:22:00Z",
  "env": "prod"
}
```

## Kubernetes probe mapping

```yaml
livenessProbe:
  httpGet: { path: /health, port: 8000 }
  periodSeconds: 10
  failureThreshold: 3
readinessProbe:
  httpGet: { path: /ready, port: 8000 }
  periodSeconds: 5
  failureThreshold: 2
```

`/version` is not used as a probe; it exists for humans and for
post-deploy smoke tests (the deploy pipeline curls `/version` and
asserts `git_sha == $GIT_SHA`).

## Vercel / serverless note

Serverless platforms do their own health via function cold-start and
response-time signals. Expose `/health` + `/ready` + `/version`
anyway — the post-deploy smoke in `rules/deploy/*.md` curls them.
Keep them cheap; they run on warm invocations too.

## Anti-patterns

- `/health` pinging the DB. Conflates liveness with readiness; one
  slow dep and the LB evicts a healthy container.
- `/ready` returning 200 even when a required dep is down. Readiness
  must be honest or auto-rollback cannot work.
- `/version` requiring auth. It must be unauth'd; the deploy
  pipeline needs it before the app is fully bootstrapped.
- Logging a warning on every `/health` hit. The probe hits every few
  seconds; a `WARN`-per-probe drowns real signal. `DEBUG` level
  only, or do not log it.
