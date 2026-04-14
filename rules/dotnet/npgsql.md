# .NET — Npgsql

Driver-specific rules for the Postgres binding. Covers types, parameters,
connection strings, pooling, and common landmines. Required reading alongside
`rules/dotnet/coding-standards.md §5` and `rules/postgres/migrations.md`.

## 1. Timestamps — UTC only

Npgsql 6+ enforces UTC for `timestamp with time zone`. See also
`coding-standards.md §5.1`.

- Column type: `timestamptz` (always). Never `timestamp without time zone`
  for wall-clock or audit data.
- .NET type: `DateTime` with `Kind=Utc`, or `DateTimeOffset` (preferred on
  public surfaces).
- Do not flip `Npgsql.EnableLegacyTimestampBehavior`; it's off by default and
  must stay off.

```csharp
// GOOD — always UTC at the boundary
entity.CreatedAt = DateTime.UtcNow;
// GOOD — offset carries timezone info explicitly
entity.PublishedAt = DateTimeOffset.UtcNow;

// BAD — Kind=Unspecified crashes SaveChangesAsync
entity.CreatedAt = DateTime.Parse("2026-01-01 12:00");
```

### `timestamp` (without tz) — when and only when

Use `timestamp without time zone` only for values that are deliberately
timezone-less (e.g., a calendar reminder bound to the user's local day, a
business-process clock tick). Document the intent on the column.

## 2. Common Postgres types → .NET types

| Postgres          | .NET                         | Notes                                     |
|-------------------|------------------------------|-------------------------------------------|
| `bigint`          | `long`                       | Prefer over `serial` for new keys.        |
| `int`             | `int`                        |                                           |
| `bigserial`       | `long`                       | Use `GENERATED ALWAYS AS IDENTITY` instead. |
| `uuid`            | `Guid`                       | `gen_random_uuid()` server-side, or v7 in .NET. |
| `text`            | `string`                     | No length limit in Postgres.              |
| `varchar(n)`      | `string` + `HasMaxLength(n)` | Enforce in EF config.                     |
| `bytea`           | `byte[]`                     |                                           |
| `timestamptz`     | `DateTime` (Utc) / `DateTimeOffset` | See §1.                              |
| `date`            | `DateOnly`                   | .NET 6+.                                  |
| `time`            | `TimeOnly`                   | .NET 6+.                                  |
| `interval`        | `TimeSpan` or `NpgsqlInterval` | `NpgsqlInterval` preserves month/year.   |
| `numeric(p,s)`    | `decimal`                    | Use `HasPrecision(p, s)` in EF config.    |
| `jsonb`           | `JsonDocument` / domain type | `HasColumnType("jsonb")` + value converter. |
| `json`            | `JsonDocument`               | Prefer `jsonb` for indexing/operators.    |
| `inet`/`cidr`     | `IPAddress` / `(IPAddress, int)` |                                       |
| `point`/`line`    | `NpgsqlPoint` / `NpgsqlLine` | Requires `Npgsql.EnableNetTopologySuite`. |
| `arrays`          | `T[]` / `List<T>`            | Emits `text[]`, `int[]`, etc.            |

### JSON

```csharp
// Entity
public JsonDocument Metadata { get; set; } = JsonDocument.Parse("{}");

// EF config
b.Property(e => e.Metadata).HasColumnType("jsonb").IsRequired();
```

For a strongly typed domain object, add a value converter:

```csharp
b.Property(e => e.Metadata)
 .HasColumnType("jsonb")
 .HasConversion(
     v => JsonSerializer.Serialize(v, JsonSerializerOptions.Default),
     v => JsonSerializer.Deserialize<Metadata>(v, JsonSerializerOptions.Default)!);
```

## 3. Parameters — always bind

Never concatenate user input into SQL — Npgsql supports `@param` and
positional placeholders across every API (EF raw SQL, `NpgsqlCommand`,
Dapper).

```csharp
// EF Core — FromSqlInterpolated is parameterized
var rows = await db.Invoices
    .FromSqlInterpolated($"SELECT * FROM invoices WHERE customer_id = {customerId}")
    .ToListAsync(ct);

// NpgsqlCommand
await using var cmd = new NpgsqlCommand("INSERT INTO t(k,v) VALUES (@k,@v)", conn);
cmd.Parameters.AddWithValue("k", key);
cmd.Parameters.AddWithValue("v", value);
```

## 4. Connection strings

Canonical form:

```
Host=<host>;Port=5432;Database=<db>;Username=<user>;Password=<pass>;
```

Useful extensions (append with `;`):

- `SslMode=Require` / `VerifyCA` / `VerifyFull` — production.
- `TrustServerCertificate=true` — dev only.
- `Include Error Detail=true` — dev/debug; leaks values in errors, never prod.
- `ApplicationName=<service>` — shows up in `pg_stat_activity`; recommended.
- `CommandTimeout=30` — seconds; per-connection default.
- `Timeout=15` — initial connect timeout, seconds.

Configuration:

- In `appsettings.json`: `ConnectionStrings:Postgres`.
- Override with env: `ConnectionStrings__Postgres` (double underscore).
- No hardcoded fallback in `Program.cs` — fail fast on missing config.

## 5. Pooling & `NpgsqlDataSource`

Npgsql 7+ exposes `NpgsqlDataSource` as the recommended registration path —
it owns the pool and lets you configure interceptors/type mapping once.

```csharp
var dataSource = new NpgsqlDataSourceBuilder(cs)
    .EnableDynamicJson()
    .Build();
builder.Services.AddSingleton(dataSource);
builder.Services.AddDbContext<AppDbContext>(
    o => o.UseNpgsql(dataSource));
```

Pooling defaults (tune when load-testing reveals a need, not before):

| Setting              | Default | Notes                                    |
|----------------------|---------|------------------------------------------|
| `Pooling`            | true    | Keep on.                                 |
| `MinPoolSize`        | 0       | Don't pre-allocate; idle connections cost. |
| `MaxPoolSize`        | 100     | Bound by Postgres `max_connections`.     |
| `Connection Lifetime`| 0       | 0 = unlimited. Set to 1800 s (30 min) under load-balancers that drop idle TCP. |
| `Connection Idle Lifetime` | 300 | seconds before idle close.           |
| `Keepalive`          | 0       | 30 s is a reasonable prod value.         |

Rule of thumb: `MaxPoolSize × N_app_instances <= Postgres.max_connections × 0.8`.

## 6. Retries & resiliency

`EnableRetryOnFailure` (EF Core) wraps commands in a retry strategy. **Known
pitfall:** this breaks user-managed transactions — see
`rules/postgres/migrations.md §6.1`. Two rules:

1. Do not enable `EnableRetryOnFailure` inside migration runtime code —
   migrations already run in one transaction each; retrying mid-migration
   leaves partial state.
2. For application code that opens its own transaction, wrap the entire
   transaction in an `IExecutionStrategy.ExecuteAsync` block so the retry
   strategy sees it as one atomic unit.

## 7. LISTEN / NOTIFY + `NpgsqlDataSource`

For event fan-out:

```csharp
await using var conn = await dataSource.OpenConnectionAsync(ct);
conn.Notification += (_, e) => channel.Writer.TryWrite(e.Payload);
await using (var cmd = new NpgsqlCommand("LISTEN invoices_events", conn))
    await cmd.ExecuteNonQueryAsync(ct);
while (!ct.IsCancellationRequested)
    await conn.WaitAsync(ct);
```

This is an **exception** to the "all DB access via EF Core" rule; architect
sign-off required. Keep listener connections separate from the request pool.

## 8. Bulk copy

`NpgsqlBinaryImporter` is 10–100× faster than `INSERT` for bulk loads:

```csharp
await using var writer = conn.BeginBinaryImport(
    "COPY invoices (id, total_cents, created_at) FROM STDIN (FORMAT BINARY)");
foreach (var row in rows)
{
    await writer.StartRowAsync(ct);
    await writer.WriteAsync(row.Id, NpgsqlDbType.Uuid, ct);
    await writer.WriteAsync(row.TotalCents, NpgsqlDbType.Integer, ct);
    await writer.WriteAsync(row.CreatedAt, NpgsqlDbType.TimestampTz, ct);
}
await writer.CompleteAsync(ct);
```

Again: exception to EF-only rule; use for batch ETL, seed scripts,
import endpoints.

## 9. Error handling

Map `PostgresException` by `SqlState`:

| SqlState | Meaning                    | Map to                        |
|----------|----------------------------|-------------------------------|
| `23505`  | unique_violation           | 409 Conflict / `AlreadyExistsException` |
| `23503`  | foreign_key_violation      | 422 Unprocessable / domain error      |
| `23514`  | check_violation            | 422 Unprocessable                     |
| `40001`  | serialization_failure      | Retry-able; transient                 |
| `40P01`  | deadlock_detected          | Retry-able; transient                 |
| `57014`  | query_canceled             | Timeout; surface as 504               |

Never catch `PostgresException` without inspecting `SqlState` — log and map.

## 10. Checklist

- [ ] `timestamptz` columns, `DateTime.Kind=Utc` everywhere
- [ ] Parameters bound, never concatenated
- [ ] `NpgsqlDataSource` registered as singleton
- [ ] Pool sized against Postgres `max_connections` budget
- [ ] `ApplicationName` set for observability
- [ ] No `EnableLegacyTimestampBehavior` switch
- [ ] Bulk paths use `BeginBinaryImport`
- [ ] `PostgresException` handlers branch on `SqlState`
