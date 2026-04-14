# Spec: Streck Asset Tracker

> Authored by `spec-writer` under `/specify` on 2026-04-14.
> Section list matches `.claude/agents/spec-writer.md` (the canonical source).

## Summary

Streck Asset Tracker is an internal HTTP API that catalogs lab assets
(microscopes, pipettes, freezers) across Streck sites, so Quality and
Facilities can track location, ownership, and calibration status without
the spreadsheet sprawl we have today.

## Stakeholders & personas

- **Lab technician (primary)** — records when an asset moves between
  benches, flags a pipette due for calibration.
- **Facilities coordinator** — runs weekly reports of assets past their
  calibration window.
- **Quality auditor** — spot-checks asset history during audits.
- **Streck internal tools engineer** — operates the service; runs
  migrations; reads logs.

## User outcomes

- Add, view, update, and retire lab assets via a stable HTTP API.
- Record and query an asset's current location and owner.
- See which assets are due for calibration inside a named window.
- Round-trip every mutation through Postgres with durable history.
- Health-probe the service from a container platform.

## Functional requirements

- **REQ-1:** The system shall accept `POST /api/v1/assets` with an
  asset payload (type, serial, manufacturer, owner_id, location_id,
  calibrated_at, calibration_due) and return `201` with the created
  asset when the payload is valid.
- **REQ-2:** The system shall return `400` with a structured
  validation error when an asset payload is missing a required field
  or fails type/format constraints.
- **REQ-3:** The system shall accept `GET /api/v1/assets/{id}` and
  return `200` with the asset body when the id exists, and `404`
  otherwise.
- **REQ-4:** The system shall accept `GET /api/v1/assets` with
  optional filters (`location_id`, `owner_id`, `calibration_due_before`)
  and return `200` with a page of matching assets.
- **REQ-5:** The system shall accept `PATCH /api/v1/assets/{id}`
  with a partial update and return `200` with the updated asset or
  `404` if missing.
- **REQ-6:** The system shall accept `DELETE /api/v1/assets/{id}`
  and return `204`; subsequent reads of the id shall return `404`.
- **REQ-7:** The system shall expose `GET /health` returning `200` and
  a payload including `status` (`ok`|`degraded`) and `db`
  (boolean round-trip check).
- **REQ-8:** The system shall persist `assets`, `locations`, and
  `owners` in Postgres. Each asset references one `location_id` and
  one `owner_id` via foreign keys.
- **REQ-9:** The system shall reject writes that reference a
  non-existent `location_id` or `owner_id` with `422` and a message
  naming the missing id.
- **REQ-10:** The system shall flow every schema change through EF
  Core migrations with both an up and a hand-authored down SQL file
  per change.

## Non-functional requirements

- **NFR-1 (performance):** The 95th percentile of `GET /api/v1/assets`
  (page of 50) shall be ≤ 200 ms against a 10k-row dataset on a
  dev-equivalent box.
- **NFR-2 (observability):** The service shall emit a structured
  `ILogger` line per request with request id, path, status, and
  duration in ms.
- **NFR-3 (security):** The service shall not expose Postgres
  credentials in logs, errors, or responses. Connection strings come
  from `ConnectionStrings:Postgres` config; env override is
  `ConnectionStrings__Postgres`.
- **NFR-4 (correctness):** All production code runs with
  `Nullable=enable`, `TreatWarningsAsErrors=true`, and zero `#nullable
  disable` directives.
- **NFR-5 (test coverage):** xUnit line coverage on
  `Streck.AssetTracker` shall be ≥ 80%.
- **NFR-6 (docker parity):** `docker compose up` shall produce a
  passing `/health` response within 60 s on a clean machine.
- **NFR-7 (budget):** Vertical slice (spec → impl → verify) completes
  under 45 minutes of wall-clock agent work.

## Acceptance criteria

- `curl -sf http://localhost:8080/health` returns HTTP 200 with
  `"status":"ok"`.
- `POST /api/v1/assets` round-trips and the same id is retrievable
  via `GET /api/v1/assets/{id}` with identical fields.
- `PATCH /api/v1/assets/{id}` with `{"location_id": "<new>"}` changes
  only the location; other fields preserved.
- `DELETE /api/v1/assets/{id}` is idempotent once (second call
  returns 404, not 500).
- `dotnet test` reports 0 failures, coverage ≥ 80% for the API
  project.
- `soup plan validate .soup/plans/asset-tracker.json` exits 0 (once
  that subcommand exists — see Open questions).
- `EF Core` migration pair `Init` applies cleanly against a fresh
  Postgres 16 instance and rolls back without residue.

## Out of scope

- User-facing web UI (no React cycle).
- Authentication / authorization (Streck SSO is a separate slice).
- Multi-tenancy (single-org for v1).
- Asset photos / attachments.
- Full audit trail (immutable event log); v1 only keeps current row.
- Cross-site replication.

## Open questions

_Resolved by `/clarify` on 2026-04-14; see `## Clarifications`._

## Clarifications

_Ran `/clarify` on 2026-04-14. Three questions surfaced and resolved:_

1. **Id format for assets/locations/owners** — resolved as **UUID v7**
   (time-ordered, insert-friendly on Postgres). Column type: `uuid`,
   default `gen_random_uuid()` for locations/owners (where
   time-ordering doesn't matter); application-generated UUID v7 for
   assets (insert hot path).
2. **Calibration due representation** — resolved as a `calibration_due`
   `timestamptz` column (nullable). Assets without a calibration
   schedule (e.g., freezers) leave it NULL. `GET /api/v1/assets?
   calibration_due_before=2026-05-01` filters by this column.
3. **Delete semantics for assets** — resolved as **hard delete** for
   v1. Rationale: v1 has no audit/history requirement; add soft-delete
   + history in a v2 spec if Quality asks for it. `DELETE` returns
   `204` on first call, `404` thereafter.
