# Metrics

Structured logs answer "what happened to this one request." Metrics
answer "what is the rate / latency / saturation of this surface."
Ship both; they are orthogonal.

## Metric types

| Type | Use for | Library primitive |
|---|---|---|
| Counter | Monotonic counts: requests, errors, jobs done | `Counter` |
| Gauge | Instantaneous state: queue depth, active connections, pool usage | `Gauge` |
| Histogram | Distribution: request latency, payload size, DB query time | `Histogram` (not `Summary` — aggregation is easier) |

## Backends

| Backend | When | Note |
|---|---|---|
| Prometheus (pull) | Self-hosted, K8s-native | Scraper hits `/metrics`; app exposes it |
| OpenTelemetry → anywhere | You want vendor-portable | Collector ships to Grafana / Datadog / App Insights |
| Application Insights | Azure-heavy shop | Push-based; wire via SDK, not `/metrics` |

**Default for soup templates: Prometheus-style pull + OpenTelemetry
SDK.** The `/metrics` endpoint is auth-scoped to the internal network
(Prometheus scraper IP, or a mesh sidecar).

## Naming convention

`<app>_<domain>_<metric>_<unit>` — all lowercase, underscores, unit
suffix mandatory.

Good:
- `shop_orders_created_total`
- `shop_checkout_latency_seconds`
- `shop_db_pool_connections_active`

Bad:
- `orders` (no app prefix, no unit, ambiguous)
- `shopOrdersCreated` (camelCase)
- `shop_latency_ms` (ms is deprecated in Prometheus convention; use
  seconds with a histogram bucket in ms)

## Units

- Time: `seconds`.
- Bytes: `bytes`.
- Counts: no unit suffix required but prefer `_total` for counters.
- Ratios: unitless, documented in the help text.

## The four golden signals

Every HTTP surface exposes:

1. **Traffic:** `<app>_http_requests_total{method, route, status}`
2. **Errors:** `<app>_http_errors_total{method, route, code}`
3. **Latency:** `<app>_http_request_duration_seconds{method, route}`
   (histogram)
4. **Saturation:** `<app>_db_pool_in_use_connections` (or equivalent
   for the bottleneck resource)

## Label cardinality — the trap

Every unique label combination creates a new time series. Naive
labels blow up storage + query cost. Rules:

- **Never label with user id, request id, correlation id, session
  id, or any high-cardinality string.** Those are log fields, not
  metric labels.
- **Never label with full URL paths.** Use a route template
  (`/users/:id` not `/users/123`). Frameworks can inject this; if
  not, do it manually in the middleware.
- **Limit label values to a bounded alphabet.** `status` bucketed to
  1xx/2xx/3xx/4xx/5xx is fine; a full HTTP code set (200/201/204/
  301/400/401/403/404/500/502/503/504) is also fine. A free-form
  `error_message` label is not.
- **Rule of thumb:** if you cannot enumerate the label values on a
  whiteboard, they do not belong in a metric label. Move them to a
  log field.

## Python example (prometheus-client)

```python
from prometheus_client import Counter, Histogram, make_asgi_app

REQS = Counter("shop_http_requests_total", "HTTP requests", ["method", "route", "status"])
DUR  = Histogram("shop_http_request_duration_seconds", "HTTP request duration",
                 ["method", "route"],
                 buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))

app.mount("/metrics", make_asgi_app())
```

## .NET example (prometheus-net)

```csharp
builder.Services.UseHttpClientMetrics();
app.UseHttpMetrics();
app.MapMetrics();  // /metrics
```

## Scraping

- Prometheus scrape interval: 15s default; 30s if cost-sensitive.
- Never expose `/metrics` publicly. Restrict via network policy or
  mesh auth; metrics carry operational intelligence.

## When NOT to add a metric

If the question is "did this specific request succeed," the answer
is a **log line** with the correlation id, not a metric. Metrics
are for rates and distributions over time, not for individual
event recall.
