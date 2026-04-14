# Structured logging (app-side)

`rules/global/logging.md` mandates the `{Domain}.{Action}_{State}`
event shape and correlation-id propagation. This rule pins the **per-
stack library** and codifies hard-stops: no `print`, no
`Console.WriteLine`, no `console.log` in shipped code.

## Library per stack

| Stack | Library | Renderer |
|---|---|---|
| Python | [`structlog`](https://www.structlog.org) >= 24 | `JSONRenderer` in prod, `ConsoleRenderer` in dev |
| .NET | [`Serilog`](https://serilog.net) + `Serilog.Sinks.Console` + `Serilog.Enrichers.Environment` | `CompactJsonFormatter` in prod |
| Node / TS | [`pino`](https://getpino.io) >= 9 | JSON by default; add `pino-pretty` dev dep only |

The template scaffold wires the JSON renderer conditional on
`NODE_ENV`, `ASPNETCORE_ENVIRONMENT`, or a soup-owned
`APP_ENV` — dev stays human-readable, prod is machine-parseable.

## Hard stops

- **No `print()` / `Console.WriteLine` / `console.log` in shipped
  code.** A code-reviewer BLOCK on any such call outside `tests/`,
  `scripts/`, or files marked `# dev-only`.
- **No string interpolation for event properties.** Pass them as
  structured fields. The global rule already forbids it; this rule
  adds: the linter config in each template bans `f"{var}"` style
  inside `log.info/warn/error` calls via a small regex check in CI.
- **No secrets, no full request bodies, no PII.** Redaction hooks
  `rules/compliance/pii.md`; structlog's `processors.format_exc_info`
  + a custom `drop_keys(["password", "token", "authorization"])`
  processor is the baseline.

## Level guidance

Inherit `rules/global/logging.md`'s table. Additions for app-side:

- **Production default: `INFO`.** `DEBUG` only via a runtime env
  knob; never on by default. A hot loop emitting `DEBUG` is a cost
  incident waiting to happen.
- **`WARN` for retries + fallbacks.** Every circuit-breaker trip,
  every degraded-dep fallback, every auth refresh retry: `WARN` with
  the retry count.
- **`ERROR` + `CRITICAL` page.** An `ERROR` that does not page is a
  `WARN`. Be honest about level.

## Sampling

Sample expensive events at the library layer, not in the emit call:

- **Head-based sampling** for hot tracing spans (rule-of-thumb: 1 in
  100 on request-path spans, 1 in 1 on errors).
- **Tail-based sampling** (keep failed traces + a base rate of
  success) via the observability backend (Sentry / App Insights /
  OpenTelemetry collector), not in-app.
- **Never sample error logs.** If it's an `ERROR`, emit it every
  time.

## Shipping

- Dev: JSON to stdout; `docker compose logs -f` or the local terminal
  suffices.
- Prod: JSON to stdout, shipped by the container runtime (Fluent Bit,
  Vector, App Insights agent, Grafana Alloy). Do not write log files
  from the app itself — let the infra layer ship stdout.

## Python example (structlog)

```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.contextvars.merge_contextvars,  # correlation_id flows here
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()
log.info("Order.Place_completed", order_id=order_id, user_hash=h)
```

## .NET example (Serilog)

```csharp
Log.Logger = new LoggerConfiguration()
    .Enrich.FromLogContext()
    .Enrich.WithProperty("service", "your-api")
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
```

## Node example (pino)

```ts
import pino from "pino";
export const log = pino({
  level: process.env.LOG_LEVEL ?? "info",
  formatters: { level: (label) => ({ level: label }) },
});
log.info({ order_id, user_hash }, "Order.Place_completed");
```
