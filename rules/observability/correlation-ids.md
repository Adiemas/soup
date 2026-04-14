# Correlation IDs

Every request that enters the system gets a `correlation_id`. It is
generated at the edge (HTTP middleware, CLI entrypoint, queue
consumer), attached to every log line in the call chain, and
propagated through outgoing calls via the `X-Request-Id` header.

`rules/global/logging.md §Correlation IDs` is the convention; this
rule is the **middleware wiring** per stack.

## The header

- Incoming: read `X-Request-Id`. If missing or malformed, generate a
  new UUID4.
- Outgoing: include `X-Request-Id: <id>` on every downstream HTTP
  call, every SQL statement attribution (via app_name or a comment),
  every queue message (as a message attribute).
- Format: UUID4 preferred. Accept any opaque ASCII under 128 chars
  from upstream — do not rewrite an upstream-supplied id.

## Log binding

Bind the correlation id to the logger for the request lifetime so
every log line inside the request carries it automatically:

- **Python / structlog:** `structlog.contextvars.bind_contextvars(
  correlation_id=cid)` at the middleware; `clear_contextvars()` at
  the end.
- **.NET / Serilog:** `LogContext.PushProperty("CorrelationId", cid)`
  inside the middleware; dispose at request end.
- **Node / pino:** use `asyncLocalStorage` + `log.child({cid})` per
  request.

## Propagation rules

- **DB calls:** include the id as a SQL comment on the statement
  (`/* cid=<id> */ SELECT ...`) so DB-side slow-query logs can be
  joined back. `psycopg` supports this via `conn.info.parameter_status`
  + `SET application_name`. For .NET, use `Npgsql` `CommandText`
  prefix. Do NOT send it as a parameter — keep the statement cache
  stable.
- **Queues:** message attribute named `correlation_id` (SQS, Kafka
  headers, Azure Service Bus properties). Consumers read it first
  thing and rebind the logger.
- **External HTTP:** set `X-Request-Id` on the outgoing request
  exactly as received / generated. Do not add a chain (some apps do
  `traceparent` for distributed tracing — that is orthogonal and
  correct; keep both headers if you use tracing too).

## Never

- **Never log PII tied to the correlation id.** The id itself is
  opaque and safe to log forever. Do not write `correlation_id=<cid>
  user_email=<email>` — log a hash. See `rules/compliance/pii.md`.
- **Never leak the correlation id cross-tenant.** If you multiplex
  tenants, scope the id to a single tenant's context; do not
  concatenate.
- **Never re-generate an id mid-request.** One request, one id, end
  to end.

## FastAPI middleware example

```python
import uuid, structlog
from fastapi import Request

@app.middleware("http")
async def correlation_id_mw(request: Request, call_next):
    cid = request.headers.get("x-request-id") or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(correlation_id=cid)
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.clear_contextvars()
    response.headers["x-request-id"] = cid
    return response
```

## Next.js middleware example

See `templates/nextjs-app-router/src/middleware.ts` for the
shipping-ready wire. It reads `x-request-id`, generates a UUID4 on
miss, sets the response header, and makes the id available to Route
Handlers via the forwarded request headers.

## ASP.NET Core example

```csharp
app.Use(async (ctx, next) => {
    var cid = ctx.Request.Headers["X-Request-Id"].FirstOrDefault() ?? Guid.NewGuid().ToString("N");
    using (LogContext.PushProperty("CorrelationId", cid)) {
        ctx.Response.OnStarting(() => { ctx.Response.Headers["X-Request-Id"] = cid; return Task.CompletedTask; });
        await next();
    }
});
```
