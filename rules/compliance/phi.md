# PHI handling (HIPAA-adjacent)

Triggered by `compliance_flags: [phi]` on the intake form. Applies to
any app that handles Protected Health Information — individually
identifiable health information in any form (electronic, paper, oral)
including diagnosis, test results, demographic data tied to a patient
encounter, MRN, and insurance identifiers.

## Not legal advice

This file describes Streck's **operational posture** for PHI. It does
not replace the HIPAA regulatory text, your BAA obligations with
counterparties, or the compliance team's written policies. Escalate
to the `requesting_team` + compliance before shipping anything net-new
touching PHI.

## Iron law

```
Assume every PHI byte is subject to breach notification. Design as if
you will have to prove — to an auditor, with logs — who read what,
when, and why.
```

## 1. Business Associate Agreement (BAA)

- **Do not ingest PHI from or send PHI to a vendor without a signed
  BAA on file.** Verify with compliance before integrating. An
  `integrations[]` entry that names a third party not covered by a
  BAA is a **blocker**, not a warning.
- Your downstream services fall under the same obligation. A
  subprocessor that is not BAA-covered is out of scope until the
  paperwork catches up — do not ship a "temporary" integration and
  promise to add the BAA later.
- The BAA is an artifact; reference it by ID in the architecture
  decision record (`docs/adr/` or `.soup/adr/`) when the integration
  lands.

## 2. Minimum necessary rule

- Collect and expose the **minimum** PHI required for the specific
  purpose. A report that needs a date-of-birth range for
  stratification does not need individual DOBs.
- Data products that aggregate PHI across records should implement
  de-identification (Safe Harbor or expert-determined) before
  leaving the PHI zone. Aggregates are easier to reason about than
  row-level access.

## 3. Access controls

- Role-based access at the route handler (not the route prefix).
  Every handler declares the role it requires and writes that to
  the audit log.
- Break-glass access (emergency override) must be recorded with
  actor + reason + automatic notification to compliance within 1
  business day.
- Session lifetime for PHI-bearing sessions is shorter than the org
  default — 1 hour idle / 8 hours absolute is a reasonable starting
  point. Override only with written rationale.

## 4. Audit logging

Every PHI access is an audit event. At minimum, log:

- Actor: user ID (not username), tied to directory entry.
- Subject: patient identifier (hashed if logged outside the PHI
  database; see §5).
- Action: `read`, `write`, `export`, `print`.
- Reason: structured code where possible (`treatment`, `payment`,
  `operations`, `research`), plus free-text when the code is `other`.
- Outcome: `success` or `denied`, with failure reason.

Audit logs are **separate from application logs** and have their own
retention (≥ 6 years from last access, per HIPAA guidance). Losing
audit logs is itself a reportable condition.

## 5. Storage & transit

- **Encryption at rest** required. Column-level for PHI fields inside
  otherwise-mixed tables; storage-level is insufficient on its own.
- **Encryption in transit** TLS 1.2+ on every hop, including
  internal-only service calls.
- **De-identification for logs.** Never log raw PHI. When a log line
  must identify a patient, log a one-way hash (SHA-256 of
  `patient_id || salt`) where the salt lives in the org secret
  store. Different salts for different environments — a dev-log hash
  must not cross-reference with a prod hash.
- **Screen captures, debug dumps, error pages.** These must redact
  PHI automatically. A stack trace showing a patient name is a
  reportable incident.

## 6. Breach notification

- If you suspect a PHI breach (any exposure to an unauthorized
  party, however brief), **stop and escalate** to compliance
  immediately. Do not attempt to fix silently.
- The law has tight notification deadlines (60 days to affected
  individuals; immediate to HHS for ≥500 records). Missing the
  deadline is its own violation.
- Do not delete evidence. Preserve logs, backups, and affected data
  for the incident response team.

## 7. De-identification

Two acceptable paths:

1. **Safe Harbor** — remove all 18 identifiers listed in
   45 CFR § 164.514(b)(2). This file does not enumerate them
   exhaustively; consult the text before writing a de-identification
   function.
2. **Expert determination** — documented methodology by a qualified
   statistician. Retain the documentation.

Never ship a "de-identification" function that was not reviewed by
compliance. A function that leaves ZIP-5 in place is not
de-identified.

## 8. Testing obligations

- Every PHI endpoint has an authz integration test with positive and
  negative cases (allowed role ≠ forbidden role).
- Audit writes are tested as part of the endpoint's integration test
  — stub logging at the infrastructure boundary and assert on fields.
- Redaction helpers have unit tests that feed known-PHI strings and
  assert the result is scrubbed.

## 9. Red flags

- "It's just a prototype" handling real PHI — no. Use synthetic data.
- Shared dev database across teams storing real PHI — blocker.
- PHI flowing into AI / LLM prompts without BAA-covered
  infrastructure — blocker.
- Email exports of PHI without encryption — blocker.
- Any log line with a first name and a diagnosis in the same record.
