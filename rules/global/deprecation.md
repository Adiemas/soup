# Deprecation policy

_Applies to every change that removes or renames a public surface.
Pair with `rules/global/brownfield.md` (read before you change) and
the `contract-drift-detection` skill (both sides of a contract move
together)._

## Iron law

```
Breaking changes ship through a deprecation cycle — never a silent removal. Parallel support ≥ 1 release.
```

## What counts as a breaking change

Any of the following on a **public surface** (externally visible
HTTP, published library symbol, database column read by > 1 service,
CLI flag documented in `--help`):

1. **Endpoint removal.** Any `DELETE /foo` effectively applied by
   removing a route in code.
2. **Field rename.** `user.displayName` → `user.display_name` at the
   JSON boundary, regardless of server-side model.
3. **Type change.** `amount: int` → `amount: string`, or enum
   `status` to bool, or nullable → non-nullable on a response.
4. **Response-shape change.** Wrapping a bare array in `{items: [...]}`,
   adding a new required field to a request body, tightening a regex
   pattern on an input.
5. **Enum value deletion or renumbering.** Dropping `status="pending"`
   or reordering protobuf enum tags.
6. **Semantic change under the same shape.** Same name, same type,
   different meaning (e.g. `timeout_ms` started expressing minutes).
   This is the worst class — signature-stable, behaviour-drifted.
7. **Default-value flip.** `include_deleted=false` → `include_deleted=true`.
8. **DB column drop or rename** that any other service reads. Use
   expand/contract migrations (see §Database).

## Additive (non-breaking) — no deprecation cycle required

- New endpoints.
- New optional fields on requests or responses.
- New enum values **when consumers are documented as
  forward-compatible** (they must ignore unknown enum values).
- Stricter input validation that's impossible to hit today (e.g.
  capping an existing length that never reached the cap).

When in doubt — treat as breaking.

## Deprecation semantics

Mark a deprecated surface in four places simultaneously:

1. **Docs.** Add a `Deprecated (since X.Y, removal Q):` row on the
   symbol in `docs/` (or the inline OpenAPI description). The
   removal window is a concrete date or version, not a vague "soon."
2. **API docstring / schema.** Set `deprecated: true` in OpenAPI,
   `[Obsolete("...", DiagnosticId = "SOUP001")]` in C#,
   `warnings.warn(DeprecationWarning(...))` in Python internal
   paths, `@deprecated` JSDoc in TS. All three targets get the same
   removal-date string.
3. **Runtime signal at the boundary.** Emit the HTTP
   [`Deprecation`](https://datatracker.ietf.org/doc/html/rfc9745) header
   on every response from the deprecated endpoint; emit a
   `Sunset:` header with the planned removal date. Callers that
   log response headers see the signal even if they never read the
   docs.
4. **Structured log warning.** One INFO-level (not WARN — WARN is
   for operational degradation) event per request:
   `API.DeprecatedCall_invoked` with `{endpoint, caller_id, removal_date}`.
   Lets ops see adoption curves before removal.

## Minimum parallel-support window

- **Internal apps** (the default Soup target) — one minor release
  cycle, which for Streck internal apps is ≥ 2 sprints (~4 weeks).
- **Shared libraries** — two minor cycles. Library consumers don't
  upgrade on the same cadence as the library ships.
- **Externally-consumed APIs** (partner-integrations, public
  portals) — one major cycle, minimum 3 months, preferably aligned
  with a stakeholder communication from product.

The window starts when the `Deprecation:` header first ships to
production, not when the code lands in main. If your deploy cadence
is weekly, a 4-week window = ≥ 4 production releases with the signal
active.

## Semver guidance for internal apps

Semver applies to internal apps too, just with a narrower audience:

- `X.Y.Z` — X bump for contract-breaking removal (post-deprecation);
  Y bump for additive breaking-off-path change (e.g. a field
  becoming required on a *new* request path); Z for bugfix-only
  releases that keep every prior contract intact.
- Never ship a Z-only release that adds or removes a field. That's
  misuse and will break consumers that pin on Z.
- Tag removal commits `feat(api)!: remove /v1/foo (deprecated since X.Y)`
  — the `!` signals the contract break to Conventional Commits
  readers + changelog generators.

## Database — expand / contract migrations

Never drop a column in the same migration that adds its replacement.
The pattern:

1. **Expand** migration — add the new column (nullable), start
   dual-writing in the app layer, backfill the old → new value.
2. **Backfill** (data migration) — one-off script committed under
   `migrations/data/`, idempotent. Run in production; verify row
   counts match.
3. **Switch reads** — app reads new column, old column unused. Ship
   this release and let it soak for at least one full deploy cycle.
4. **Contract** migration — drop the old column. Runs *after* §2 and
   §3 are in every running instance.

Collapsing §1 and §4 into one migration is the #1 cause of
zero-downtime migration incidents. `sql-specialist` rejects this
shape by default.

## Controller deprecation template — Python (FastAPI)

```python
from fastapi import APIRouter, Response
import warnings

router = APIRouter()

@router.get(
    "/v1/user/{user_id}/profile",
    deprecated=True,  # flips OpenAPI `deprecated: true`
    responses={
        200: {
            "headers": {
                "Deprecation": {
                    "description": (
                        "RFC 9745 deprecation marker. Use "
                        "GET /v2/users/{id} instead."
                    ),
                    "schema": {"type": "string"},
                },
                "Sunset": {
                    "description": "Removal target date (RFC 7231).",
                    "schema": {"type": "string"},
                },
            },
        },
    },
)
async def get_profile_v1(user_id: str, response: Response) -> dict:
    """DEPRECATED — removal target 2026-07-01. Use GET /v2/users/{id}."""
    warnings.warn(
        "GET /v1/user/{id}/profile is deprecated; use /v2/users/{id} "
        "(removal 2026-07-01).",
        DeprecationWarning,
        stacklevel=2,
    )
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 01 Jul 2026 00:00:00 GMT"
    log.info(
        "API.DeprecatedCall_invoked",
        extra={
            "endpoint": "/v1/user/{id}/profile",
            "removal_date": "2026-07-01",
        },
    )
    return await _profile_service.get(user_id)
```

## Controller deprecation template — C# (ASP.NET Core)

```csharp
using System;
using Microsoft.AspNetCore.Mvc;

[ApiController]
[Route("v1/users/{id:guid}")]
public sealed class UserV1Controller : ControllerBase
{
    private static readonly DateTimeOffset SunsetOn =
        DateTimeOffset.Parse("2026-07-01T00:00:00Z");

    /// <summary>
    /// DEPRECATED — removal target 2026-07-01. Use <c>GET /v2/users/{id}</c>.
    /// </summary>
    [HttpGet("profile")]
    [Obsolete(
        "Use GET /v2/users/{id}. Removal target 2026-07-01.",
        DiagnosticId = "SOUP001"
    )]
    public IActionResult GetProfile(Guid id)
    {
        Response.Headers["Deprecation"] = "true";
        Response.Headers["Sunset"] = SunsetOn.ToString("R");
        _logger.LogInformation(
            "API.DeprecatedCall_invoked {Endpoint} {RemovalDate}",
            "/v1/users/{id}/profile",
            SunsetOn
        );
        return Ok(_service.GetProfile(id));
    }
}
```

## Checklist before shipping a deprecation

- [ ] Deprecation target date is a concrete date, not "eventually."
- [ ] All four signals (docs, docstring, header, log) ship together.
- [ ] Replacement surface is live *and tested* before the deprecation
      window opens.
- [ ] Changelog entry under `[Deprecated]` section of the release
      notes.
- [ ] Dashboards / telemetry track call volume to the deprecated
      surface — removal day should show near-zero.
- [ ] Consumers have been notified (for published libs / external
      APIs, add a stakeholder comms step to the spec).

## Related

- `rules/global/brownfield.md` — the read-before-you-change loop.
- `contract-drift-detection` skill — source-of-truth side of
  contracts moves with the deprecation, both sides together.
- `brownfield-baseline-capture` skill — the baseline diff surfaces
  silent removals. A post-run diff showing a missing endpoint that
  *wasn't* deprecated is a blocker.
- `rules/global/change-budget.md` — deprecation cycles span multiple
  PRs; the change-budget governs each PR's size within that cycle.
