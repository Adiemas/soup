# Global logging rules

## Event name format

`{Domain}.{Action}_{State}`

- `Domain` — the business or system area (`Order`, `Payment`, `Spec`, `Plan`, `Agent`).
- `Action` — verb-noun in camel case (`Process`, `CreateUser`, `RunStep`).
- `State` — one of `_started`, `_completed`, `_failed`, `_skipped`, `_deferred`.

**Examples:**
- `Order.Process_started`
- `Payment.Refund_failed`
- `Agent.RunStep_completed`
- `Plan.Validate_failed`

## Structured properties (not string interpolation)

Bad (Python):
```python
log.info(f"User {user_id} placed order {order_id}")
```
Good:
```python
log.info("Order.Place_completed", extra={"user_id": user_id, "order_id": order_id})
```

Bad (C#):
```csharp
logger.LogInformation($"User {userId} placed order {orderId}");
```
Good:
```csharp
logger.LogInformation("Order.Place_completed {UserId} {OrderId}", userId, orderId);
```

## Correlation IDs

- **Every request gets a `correlation_id`** at the first entry point (HTTP middleware, CLI entrypoint, agent spawn).
- Propagate through the full call stack — middleware → service → data layer → external calls.
- Include in EVERY log line in the call chain.
- Log `correlation_id=<uuid>` on failures, even in error paths.

## Levels

| Level | Use for |
|---|---|
| `TRACE` / `DEBUG` | Development only; never enabled in prod by default |
| `INFO` | State transitions, user-observable events |
| `WARN` | Degraded behavior, fallbacks activated, retries |
| `ERROR` | Failed operations that user will see or retry |
| `CRITICAL` / `FATAL` | Process-ending errors; pager-worthy |

## Never log

- Secrets (passwords, tokens, keys, PATs, API keys)
- Full request/response bodies (log metadata: content-length, content-type, status; log body only on error and only after redaction)
- PII (emails, names, SSN, etc.) — log hashed identifiers if needed
- Stack traces from user-supplied input paths (can leak filesystem structure)

The `post_tool_use.py` hook redacts values of keys matching `(?i)(secret|token|key|password|pat|bearer)` in all session logs.

## Agent-specific

Every subagent spawn logs on start and completion:

```
Agent.Spawn_started  agent=<name> step=<S1> model=<sonnet> session_id=<uuid>
Agent.Spawn_completed agent=<name> step=<S1> duration_ms=<n> status=<pass|fail>
```

## Aggregation

- Python: `structlog` bound logger per module, JSON renderer for prod
- C#: `Serilog` with `.Enrich.FromLogContext()` and JSON sink
- Frontend: structured console via `console.info(event_name, {props})`; ship to backend via `/api/telemetry` in production

## Streaming to observability

Ship to stdout JSON in dev, JSON to file+forwarder in prod. Never emit to `print()` or `Console.WriteLine()` in shipped code.
