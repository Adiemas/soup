# Financial data (SOX-adjacent)

Triggered by `compliance_flags: [financial]` on the intake form.
Applies to any app that reads from or writes to general-ledger-adjacent
data, revenue recognition, accounts payable/receivable, or data
material to Streck's financial statements.

## Iron law

```
Every change to financial data is attributable, immutable, and
reviewed. Deploy paths separate "who wrote it" from "who released it."
```

## 1. Immutable audit trail

- Every mutation of a financial record writes an append-only audit
  row capturing: actor, timestamp (UTC), prior value, new value,
  reason (structured code + free-text), and the approval reference
  if approvals are required.
- Audit tables are append-only at the database privilege layer. The
  application role has `INSERT` on the audit table and `SELECT` on
  the audit views; `UPDATE` and `DELETE` are not granted.
- Retention matches the applicable statute — **7 years** from fiscal
  close is the default; consult finance before shortening.
- Audit integrity is checked. A nightly job verifies row counts
  monotonically increase and hashes chain correctly when hash-chain
  auditing is enabled.

## 2. Segregation of duties

SOX requires separation between roles that can modify financial data
and roles that can approve releases of that data.

- The engineer who writes the migration MUST NOT be the engineer who
  approves the deploy. Enforced by CODEOWNERS + branch protection
  (same account cannot author AND approve a PR touching
  `migrations/financial*`).
- Production deploy credentials are not present on engineer
  workstations. Deploys run through a pipeline whose approvals are
  logged.
- Break-glass access (direct DB connection to prod by an engineer)
  is recorded, time-boxed, and alerts finance within 1 business day.

## 3. Idempotency

- Financial writes are idempotent. An idempotency key covers
  customer-facing actions (invoice generation, posting an entry).
- Retry loops never produce duplicate journal entries. If the
  framework cannot guarantee idempotency, surface the gap and
  escalate before shipping.

## 4. Reconciliation

- Any app that derives a balance from inputs has a reconciliation
  procedure: the sum of journal entries matches the derived balance
  to the penny. The reconciliation is scheduled (nightly minimum)
  and alerts on divergence.
- Never mask a reconciliation break with a manual adjustment inside
  the same system. Breaks go into an incident queue with a visible
  owner.

## 5. Change management

- Schema changes to financial tables require architect + finance
  sign-off, recorded in an ADR.
- Bug fixes that change historical totals are forbidden without an
  explicit restatement plan. The "bug" is a feature of the records —
  correct forward with compensating entries.

## 6. Testing obligations

- Every mutation endpoint has an integration test that asserts the
  audit row is present with correct columns — not just a unit test
  stubbing the logger.
- Property-based tests on arithmetic: for every set of entries,
  sum(debits) == sum(credits). A type-check is insufficient.
- Deployment dry-run verifies segregation of duties: a PR from the
  migration's author cannot self-approve in the test harness.

## 7. Red flags

- "We'll add the audit column later." No — it is pre-mutation
  infrastructure.
- Bulk updates to financial tables via ad-hoc SQL — blocker without
  finance approval and a written plan.
- Any path where a single human account can both author and release
  a financial change.
- Float types for money. Use `Decimal` in Python, `decimal(18, 4)`
  or currency-specific precision in SQL.
