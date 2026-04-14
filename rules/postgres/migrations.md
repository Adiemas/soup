# Postgres — migrations

Target: PostgreSQL 16. Python stack uses Alembic + sqlc; .NET stack uses EF Core migrations. Rules below apply regardless of the driver.

## 1. Authorship

1. **Only the `sql-specialist` agent writes migrations.** Other agents propose, this agent authors.
2. Every schema change is a migration file committed to the repo. No ad-hoc `psql` on shared environments.
3. Migration file name encodes a timestamp + human-readable slug: `2026_04_14_123045_add_invoices_partial_payments.sql` (or the framework-default equivalent).

## 2. Forward + back pairs

1. Every migration has **both** a forward (`upgrade` / `up`) and a back (`downgrade` / `down`) section.
2. Down must actually undo: drop the column, drop the table, drop the index. If undo is genuinely lossy (dropping a table that had rows), the down section still runs but is documented: a header comment describes what's unrecoverable.
3. Irreversible operations (e.g., enum value removal on shared dev data) require explicit written approval in the commit body and must be justified — no silent "one-way" migrations.

## 3. No runtime DDL

1. App code **never** runs `CREATE`, `ALTER`, or `DROP` at request time. These run only in the migration pipeline.
2. `CREATE TEMP TABLE` inside a query is allowed (session-scoped). `CREATE TABLE IF NOT EXISTS` from app code is not.
3. No schema auto-sync on startup. EF Core `Database.EnsureCreated()` is banned in non-test code; use migrations.

## 4. Idempotency & safety

1. Every forward migration is safe to run once. The migration tool (Alembic / EF) tracks which have run; don't re-apply manually.
2. Use `IF NOT EXISTS` / `IF EXISTS` guards when dropping constraints that a prior environment may or may not have — helps multi-env reapply.
3. Prefer additive changes that deploy independently of code (new column nullable, new index `CONCURRENTLY`). Remove the column in a later migration, after the code no longer references it — the **expand/contract** pattern.

```sql
-- V1: expand (additive, safe to deploy before new code)
ALTER TABLE invoices ADD COLUMN balance_cents integer NOT NULL DEFAULT 0;

-- V2: (after code rollout) start writing from the app

-- V3: contract (after confidence window)
ALTER TABLE invoices ALTER COLUMN balance_cents DROP DEFAULT;
```

## 5. Indexes

1. Build indexes `CONCURRENTLY` in production:
   ```sql
   CREATE INDEX CONCURRENTLY idx_invoices_customer_id ON invoices (customer_id);
   ```
2. Alembic: `op.create_index(..., postgresql_concurrently=True)` **and** set the migration `atomic = False`.
3. EF Core: use raw SQL in the migration for `CONCURRENTLY`; EF does not emit it by default.
   ```csharp
   protected override void Up(MigrationBuilder migrationBuilder)
   {
       migrationBuilder.Sql(
           "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_invoices_customer_id " +
           "ON invoices (customer_id);",
           suppressTransaction: true);
   }

   protected override void Down(MigrationBuilder migrationBuilder)
   {
       migrationBuilder.Sql(
           "DROP INDEX CONCURRENTLY IF EXISTS idx_invoices_customer_id;",
           suppressTransaction: true);
   }
   ```
4. Unique indexes that cover NULL semantics correctly: remember `NULL != NULL` — use `INDEX NULLS NOT DISTINCT` (PG 15+) when NULLs should collide.
   ```sql
   CREATE UNIQUE INDEX ux_customers_email
     ON customers (email) NULLS NOT DISTINCT;
   ```
5. **Partial indexes** when the predicate is sparse (e.g., only active rows):
   ```sql
   CREATE INDEX idx_invoices_open_due ON invoices (due_at)
     WHERE status = 'open';
   ```
   Partial indexes are smaller, faster to maintain, and often enable index-only
   scans. Prefer over full indexes for soft-delete (`deleted_at IS NULL`) and
   state-machine (`status = 'open'`) queries.
6. **Expression indexes** for computed lookups:
   ```sql
   CREATE INDEX idx_customers_email_lower ON customers (lower(email));
   ```

## 6. Transactions

1. Each migration runs in one transaction by default. Use that — atomic success/fail is good.
2. Statements that can't run in a transaction (`CREATE INDEX CONCURRENTLY`, `ALTER TYPE ... ADD VALUE`) require opting out: Alembic `transactional_ddl = False`, EF `migrationBuilder.Sql(..., suppressTransaction: true)`.
3. Long-running migrations must use batched updates to avoid lock contention on large tables:
   ```sql
   -- update 10k rows at a time with a short sleep between batches
   ```

### 6.1 EF Core — `EnableRetryOnFailure` breaks migrations

`EnableRetryOnFailure` wraps every EF operation in a retry loop. **Do not enable
this on the migration-runner connection**: a migration is already one
transaction, and retrying mid-migration can re-apply partial changes. Use a
plain `UseNpgsql(cs)` for migrations; enable retries on application-runtime
connections only if you also wrap user transactions in
`IExecutionStrategy.ExecuteAsync`.

## 6a. Expand / contract pattern (column drops, renames)

Never drop or rename a column in a single migration deploy. Use a three-step
pattern (already shown in §4 at the rename level; apply it to typed changes
too):

```sql
-- V1 (expand): add the new, nullable column; deploy before code uses it.
ALTER TABLE invoices ADD COLUMN total_minor_units bigint;

-- V2 (backfill): a separate migration that copies data, in batches.
UPDATE invoices
SET total_minor_units = total_cents
WHERE total_minor_units IS NULL
  AND id BETWEEN 0 AND 10000; -- and so on, batched

-- V3 (tighten): after the backfill has run & code writes both columns,
-- enforce NOT NULL and drop the old column.
ALTER TABLE invoices ALTER COLUMN total_minor_units SET NOT NULL;
ALTER TABLE invoices DROP COLUMN total_cents;
```

Each step is independently deployable; each leaves the system in a valid
state even if the next step is delayed or rolled back.

## 7. Constraints & data integrity

1. Prefer database-enforced constraints: `NOT NULL`, `CHECK`, `FOREIGN KEY`. Don't rely on app-layer validation alone.
2. Use `GENERATED ALWAYS AS IDENTITY` for surrogate keys on new tables (over `SERIAL`).
3. UUID PKs: `uuid` type + `gen_random_uuid()` (pgcrypto) or app-generated v7 UUIDs for time-ordered inserts.
4. **Timestamps: `timestamptz`, always.** Never `timestamp without time zone` for wall-clock or audit data. Default `now()` for audit columns. `timestamp without tz` is acceptable only for deliberately timezone-less values (business-process ticks, calendar reminders bound to the user's local day) — document the intent in a column comment. See `rules/dotnet/npgsql.md §1` for the .NET side (Npgsql UTC enforcement).
5. FKs must declare `ON DELETE` (and usually `ON UPDATE`) policy. Options: `RESTRICT` (default), `CASCADE`, `SET NULL`, `SET DEFAULT`, `NO ACTION`. Never leave implicit.

## 8. Naming

```
table:    invoices                  (plural, snake_case)
column:   total_cents, created_at   (snake_case)
pk:       invoices_pkey             (Postgres default is fine)
fk:       invoices_customer_id_fkey
index:    idx_invoices_customer_id
unique:   ux_invoices_external_id
check:    ck_invoices_total_nonneg
```

## 9. Env parity

1. Dev, CI, staging, and prod run the **same** migration files in the **same** order.
2. Environment differences are in config (connection strings, feature flags), not in schema.
3. CI spins up an ephemeral Postgres (Testcontainers or the `postgres` service in GH Actions) and runs every pending migration, then the test suite against it.

## 10. Data migrations

1. Data migrations live in a migration file of their own — never mixed with schema changes in the same file.
2. Batch updates; avoid full-table `UPDATE` without a `WHERE` bounded by indexed columns.
3. For big backfills, consider a one-off script (checked in, tagged with the migration it supports) run outside the migration tool.

## 11. Observability — `pg_stat_statements`

Enable the extension during provisioning (not inside an app migration — it
needs `shared_preload_libraries`):

```sql
-- In a provisioning migration run by the DBA / infra pipeline:
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

`pg_stat_statements` must also be in `postgresql.conf`'s
`shared_preload_libraries`. In Docker/compose, set the server command:

```yaml
services:
  db:
    image: postgres:16-alpine
    command:
      - "postgres"
      - "-c"
      - "shared_preload_libraries=pg_stat_statements"
      - "-c"
      - "pg_stat_statements.track=all"
```

Query it:

```sql
SELECT query, calls, total_exec_time, mean_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Use this in incident reviews and weekly slow-query triage — it's the cheapest
observability win on any Postgres deployment.

## 12. SQL vs PL/pgSQL functions

1. Default to **SQL** functions when the body is one expression or query —
   the planner can inline them, and they can be marked `IMMUTABLE` /
   `STABLE` for caching and index eligibility.
   ```sql
   CREATE OR REPLACE FUNCTION invoice_balance(inv invoices)
   RETURNS bigint
   LANGUAGE sql
   IMMUTABLE
   AS $$
     SELECT inv.total_cents - coalesce((SELECT sum(amount_cents)
                                        FROM payments p
                                        WHERE p.invoice_id = inv.id), 0)
   $$;
   ```
2. Use **PL/pgSQL** only when you need procedural control (loops,
   conditionals, variable binding, exception handling):
   ```sql
   CREATE OR REPLACE FUNCTION apply_late_fee(inv_id uuid)
   RETURNS void
   LANGUAGE plpgsql
   AS $$
   DECLARE
     fee bigint;
   BEGIN
     SELECT calculate_fee(inv_id) INTO fee;
     IF fee > 0 THEN
       UPDATE invoices SET total_cents = total_cents + fee WHERE id = inv_id;
     END IF;
   END $$;
   ```
3. Avoid `LANGUAGE plpython3u` / `plperlu` in migration files — they require
   trust-level extensions that aren't available on most managed Postgres
   offerings and expand the attack surface. Ban in the wrapper-level write
   guard (`cli_wrappers/psql.py`).
4. Every function ships with a test — for PL/pgSQL, `pgtap`-style tests are
   ideal; minimally, add xUnit / pytest integration tests that cover
   expected return shapes.

## 13. Checklist

- [ ] Forward + back sections both implemented (or irreversibility justified)
- [ ] No runtime DDL in app code
- [ ] Indexes on large tables built `CONCURRENTLY`
- [ ] Expand/contract used for column removal/type change
- [ ] Migration tested against a fresh DB in CI
- [ ] Constraints declared at the DB layer, not only in code
- [ ] Every FK has explicit `ON DELETE` policy
- [ ] All wall-clock columns are `timestamptz`
- [ ] `NULLS NOT DISTINCT` chosen explicitly on unique indexes where NULL matters
- [ ] Partial / expression indexes used where they pay off
