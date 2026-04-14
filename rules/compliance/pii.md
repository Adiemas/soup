# PII handling

Triggered by `compliance_flags: [pii]` on the intake form. Applies to
any app that stores, transmits, or derives from personally
identifiable information — names, emails, phone numbers, employee
IDs, addresses, government IDs, or any combination that re-identifies
an individual.

## Iron law

```
Minimize what you collect, encrypt what you store, hash what you log,
and honor delete requests within the declared window.
```

## 1. Data minimization

- Collect only the fields that an `inputs[]` entry on the intake form
  justifies. If no intake input names a field, it has no business
  being in the schema.
- Do not "future-proof" PII columns. Add them when the feature
  arrives, not speculatively.
- Derived PII counts as PII. A `hash(email)` column used as a join
  key is still covered — treat it with the same controls.
- Pseudonymize for analytics: export `user_id` surrogates, not
  original identifiers, to downstream BI tools.

## 2. Encryption

- **At rest:** transparent disk encryption is table stakes; it does
  **not** satisfy this rule. PII columns must be either:
  - Inside a Postgres schema with column-level encryption (pgcrypto
    or Azure Managed Identity-backed key), **or**
  - Inside a separate database instance whose credentials are scoped
    to the service that owns the PII.
- **In transit:** TLS 1.2+ on every hop. Internal service-to-service
  calls are not exempt. No HTTP-on-localhost "for testing" in shared
  dev environments.
- **Backups** inherit the same encryption posture. If the primary is
  encrypted and the backup is plaintext, the backup is the breach.

## 3. Right-to-delete

- Every PII-bearing table has a documented deletion path:
  - The table itself (the row goes away), **and**
  - Every downstream cache / materialized view / search index.
- Implement deletion as a background job triggered by a request row
  in a `pii_deletion_requests` table with columns `(request_id,
  user_id, requested_at, completed_at, evidence_ref)`.
- Deletion SLA: **30 days** from request to completion. Track
  completion with an artifact (log reference, receipt).
- Soft-delete is **not** compliance deletion. A `deleted_at` flag
  that leaves the row queryable does not discharge the obligation.

## 4. Logging discipline

- **Never log raw PII.** Not email, not phone, not name, not
  employee ID.
- When a log line must identify the actor, log a stable one-way hash
  of the identifier (SHA-256 of `user_id || per-env salt`). The salt
  lives in the org secret store, not the repo.
- Treat request bodies as untrusted for log purposes — strip PII
  fields before any structured log emission.
- If you observe a PII leak in logs, rotate the affected sink (do
  not just delete log lines — the leak already happened) and file an
  incident.

## 5. Access controls

- Default deny. PII endpoints require an explicit role check on the
  request handler — not just route-level auth.
- Row-level security in Postgres when multiple tenants share a
  schema. A team accidentally reading another team's PII is a
  breach.
- Audit every read of a PII table at the database level when the
  caller is an admin or support role. User-initiated reads are
  exempt from the audit log (they already have the data).

## 6. Third-party processors

If a feature sends PII to an external service (analytics, email,
support tooling), list the processor on the intake form's
`integrations[]` with `auth` populated. An un-listed processor
reached via a hard-coded client is a finding — the intake form is
the contract.

## 7. Testing

- Unit tests for redaction helpers (`redact_email`,
  `hash_for_log`) — catch regressions where someone removes the
  redaction step.
- Integration tests for deletion: delete a row, query every downstream
  cache / index / backup *sample* within the test harness, assert
  absence.
- Include a "PII in logs" linter in CI: grep for common PII patterns
  (email regex, phone regex) in the `logging/` output of a known test
  run; fail the build on any hit.

## 8. Red flags

- "We'll hash it before it hits the log" at implementation time —
  write the helper first, then write the feature.
- "The user asked for it in clear text" — display-time rendering is
  a different concern from storage / logging. The storage rule still
  applies.
- "PII anonymization for training data" — real anonymization is
  harder than it looks; escalate before exporting anything derived
  from PII outside its system of record.
