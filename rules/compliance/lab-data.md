# Lab data — Streck operational context

Triggered by `compliance_flags: [lab-data]` on the intake form. Applies
to any app that reads, writes, or derives values from laboratory
operations data — calibration logs, QC samples, assay runs, specimen
tracking, instrument telemetry, reagent lots.

## Iron law

```
Lab data records are evidence. Every write must be auditable, every
read must be attributable, and no value may be silently overwritten.
```

Lab data is not "just another database table." Streck operates in a
CAP / CLIA-adjacent environment where instrument outputs, calibration
history, and QC records may be subpoenaed or audited for regulatory
compliance. Treat every row as a signed record from the instant it
lands.

## 1. Retention

- **7-year minimum** for records tied to a reported result (QC,
  calibration, reagent lot, specimen assay). Implement retention at
  the storage layer (`ARCHIVED` columns, partition retention, S3
  lifecycle policies) — not in application code.
- **Never hard-delete** a record that has downstream references in
  other tables. Prefer soft-delete (`deleted_at TIMESTAMPTZ NULL`)
  plus a `deletion_reason TEXT NOT NULL` audit column.
- Do not truncate logs that reference lab data. If you must roll logs,
  archive first.

## 2. Audit trail (required on every mutation)

Every `INSERT`/`UPDATE`/`DELETE` against a lab-data table must record,
atomically with the change:

- Actor: user ID (not username), service account ID, or instrument
  ID. Never `null`; use a sentinel (`system:migration:0001`) if
  humans are not involved.
- Timestamp: `TIMESTAMPTZ` with timezone. UTC in storage, local only
  on display.
- Reason: free-text `change_reason` column or structured enum when
  the universe of reasons is small.
- Prior value: store the pre-change row in an append-only history
  table, not just a diff.

Audit rows are append-only. Never `UPDATE` or `DELETE` an audit row;
corrections go in as compensating entries with a reference to the
original.

## 3. No PHI without explicit opt-in

Lab-data apps default to **no PHI**. If a feature requires patient
identifiers, the intake form must *also* carry the `phi` flag — the
`subagent_start.py` hook then injects `rules/compliance/phi.md`
alongside this one. If you notice PHI creeping into a `lab-data`-only
app (e.g. a new field captures MRN), stop and escalate; do not file
it under lab-data alone.

## 4. CAP / CLIA considerations

This framework is **not** a CAP/CLIA certification substitute. It
provides the operational guardrails that make certification tractable:

- **Instrument linkage.** Any value derived from instrument output
  must record the instrument serial + firmware version at capture
  time, not at read time.
- **Reagent lot tracing.** Any assay result records the reagent lot
  number used. If the lot is unknown, fail the write; do not default
  to `unknown`.
- **Two-person rule for corrections.** Retroactive edits to reported
  results require dual attestation in the audit trail (`actor_id` +
  `reviewer_id`, both non-null).
- **Review the Streck quality manual** before designing new
  calibration or QC features. This file does not encode the full
  process; it encodes the *code-level* expectations.

## 5. Logging

- Structured JSON logs, one line per event.
- **Log the identifier, not the payload.** A log line is `specimen
  processed: id=<uuid>`, never the specimen result value. Result
  values live in the audit table, not the log stream.
- Redact instrument serial numbers from logs destined for
  non-production sinks (dev, staging).

## 6. Testing obligations

- Every mutation endpoint must have an integration test that asserts
  the audit row was written with the expected columns. A unit test
  stubbing the audit logger is insufficient.
- Retention policies are tested in migration test suites (the
  `7-years-from-now` fixture should not be deleted by today's prune
  job).

## 7. Red flags

- "We'll add the audit table later." No — it is upstream of the
  mutation.
- "This column is redundant with the audit." Redundant data in a
  regulated column is fine; silently dropping it is not.
- Bulk deletions via ad-hoc SQL against lab-data tables — never,
  without compliance sign-off and an ADR.
