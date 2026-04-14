# Observability rules

App-side observability conventions that soup injects into every
scaffolded service. These complement `rules/global/logging.md` (which
covers event-naming conventions and is always global-injected) by
specifying concrete library choices, endpoint contracts, and the
cardinality guardrails that keep a dashboard cheap.

`rules/global/logging.md` is the **convention** layer (event names,
level guidance, correlation-id mandate). `rules/observability/*.md` is
the **implementation** layer — per-stack libraries, middleware, health
endpoints, error tracking, metrics. Both apply; the observability rules
assume the global rule has already set the event-naming ground truth.

## Rule table

| Rule | When it applies | Routed to | Related |
|---|---|---|---|
| `structured-logging.md` | Any long-running process shipping logs to prod (Python `main.py`, .NET `Program.cs`, Node entry) | `**/main.py`, `**/Program.cs`, `**/app/route*.ts`, `**/src/index.ts` | `rules/global/logging.md`, `rules/python/*`, `rules/dotnet/*` |
| `correlation-ids.md` | HTTP surface, queue consumers, scheduled jobs | Any entry-point file above | `rules/global/logging.md` (§Correlation IDs) |
| `health-readiness.md` | Any service with a network listener | Same entry-points + `**/api/health/route.ts`, `**/api/ready/route.ts` | K8s probes, load-balancer health checks |
| `error-tracking.md` | Any user-facing service; optional for CLIs | Entry-points above + `**/observability.py`, `**/observability.ts` | `rules/compliance/pii.md`, `rules/compliance/lab-data.md` |
| `metrics.md` | Anything with a meaningful throughput or latency SLO | Entry-points + `**/metrics/*.py` | Prometheus / App Insights backends |

## Routing contract

`.claude/hooks/pre_tool_use.py` injects these rules when an agent
edits a file matching the glob column above. A single edit on
`app/main.py` triggers all five rules in one context block, so the
implementer writes correlation-id middleware, health endpoints, and
error-tracking init together rather than in five separate passes.

The rules are intentionally short and recipe-shaped. Long-form
discussion belongs in `docs/ARCHITECTURE.md §7` (observability
pillar); these rules are what a code-writing subagent needs in its
fresh context.

## Relationship to runbooks and incidents

- `rules/observability/*.md` = how to **instrument** an app so the
  signal exists.
- `docs/runbooks/*.md` = known environmental failures + fixes.
- `docs/incidents/*.md` = novel failures in production; each writes a
  postmortem using `docs/incidents/TEMPLATE.md`.

The `incident-responder` agent reads from the instrumentation these
rules produce — if a template ships without structured logs or
correlation ids, incident response degrades to grep-and-pray. Keep
these rules short, keep them enforced at scaffold time.
