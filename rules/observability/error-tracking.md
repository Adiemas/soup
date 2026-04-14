# Error tracking

Exceptions that escape the request handler (or the background worker)
are shipped to an error-tracking backend. Pick one per app; do not
dual-ship.

## Vendor options

| Vendor | When to pick | Notes |
|---|---|---|
| Sentry | Default for OSS / Supabase / generic stacks | Great stack-trace grouping; strong PII scrubbing hooks |
| Application Insights | You are deep on Azure + already using Azure Monitor | Ties into distributed tracing automatically |
| Rollbar / Bugsnag | Existing org standard | No strong opinion; use what ops already watches |

**Default for soup templates: Sentry.** Switch only with written
rationale in the intake form or ADR.

## Init pattern

- Init early, at module load (FastAPI: before `FastAPI()` instance;
  Next.js: in `instrumentation.ts`; .NET: in `Program.cs` before
  `builder.Build()`).
- Gate on env: `SENTRY_DSN` unset → the SDK init is a no-op. Never
  crash app boot because telemetry is misconfigured.
- Tag `release` with the git SHA. Same value as `/version`'s
  `git_sha`. Without this, release-comparison dashboards are noise.

## PII scrubber

Before-send hook drops known-PII keys and hashes anything that could
be a user identifier. `rules/compliance/pii.md` is the source of
truth for what counts as PII; this rule wires the scrubber.

```python
def before_send(event, hint):
    user = event.get("user") or {}
    if "email" in user: user["email"] = "<redacted>"
    if "ip_address" in user: user["ip_address"] = None
    # scrub known-bad keys from request data
    req = event.get("request") or {}
    for k in ("authorization", "cookie", "x-api-key"):
        req.get("headers", {}).pop(k, None)
    return event

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    release=os.environ.get("GIT_SHA", "dev"),
    environment=os.environ.get("APP_ENV", "dev"),
    traces_sample_rate=0.1,
    before_send=before_send,
    send_default_pii=False,
)
```

## Sampling

- **Errors:** 1.0 (every error captured).
- **Traces:** 0.1 in prod (10%), 1.0 in dev. Tune per-endpoint via
  the backend's dynamic sampling where available.
- **Releases:** tag every event with release = git SHA; enables
  "errors introduced in this release" alerts.

## Alerting thresholds

Default alerts, tuned per app in the backend UI:

- **New issue in the latest release** → page on-call immediately.
- **Issue regression (resolved → reopened)** → page on-call.
- **Error rate on `/api/*` > 1% over 5 min** → page.
- **Error rate on `/api/*` > 0.1% over 15 min** → warn; log-only.

Wire these to the on-call channel the `incident-responder` agent is
authorized to read from (Slack webhook, PagerDuty, Teams).

## Hard stops

- **Never capture request bodies unredacted.** The before-send hook
  must strip auth headers, cookies, and PII. Assume the dashboard is
  over-the-shoulder-visible.
- **Never capture logs as breadcrumbs verbatim.** If structured
  logging carries a user id, the breadcrumb will too. Pre-filter.
- **Never share the DSN across apps.** One app per project in the
  backend. Cross-app noise makes alerts useless.
- **Never capture 4xx as errors.** 4xx is user input; 5xx is the
  server's fault. Default Sentry config does this right; do not
  override.

## Release tagging

Surface the SHA three places:

1. `/version` endpoint response (see `health-readiness.md`).
2. Every error event in the tracker (via `release` tag).
3. Every structured log line (via a `service_version` field set at
   logger init).

When an incident fires, the `incident-responder` agent triangulates
across all three to isolate "did this ship in the latest release?".
