# Npgsql — `DateTime` / `timestamptz` kind mismatch

## Symptom

One of these exceptions from an EF Core query or raw Npgsql command:

```
System.InvalidCastException: Cannot write DateTime with Kind=Unspecified
to PostgreSQL type 'timestamp with time zone', only UTC is supported.
```

```
System.InvalidOperationException: The property 'X.Y' is of type
'DateTime' but the database column 'timestamptz' requires UTC.
```

Often shows up the first time a record written by a legacy store is
read by an EF Core 8 / Npgsql 8 app, or after upgrading Npgsql to 6+.

## Cause

Npgsql 6.0 tightened `timestamptz` handling: only `DateTime` values
with `Kind == DateTimeKind.Utc` round-trip cleanly. Values with
`Kind.Unspecified` or `Kind.Local` are rejected outright. Previous
Npgsql releases silently coerced them, which produced subtle UTC-vs-
local bugs — the strictness is the fix, but it breaks a lot of code
on upgrade.

This is codified in `rules/dotnet/npgsql.md`. This runbook is the
operator-facing version of that rule: symptom-first, copy-pasteable.

## Fix

### Read path — materialize as UTC

When reading:

```csharp
// EF Core value converter once, in your DbContext:
modelBuilder
    .Entity<User>()
    .Property(u => u.CreatedAt)
    .HasConversion(
        v => v.ToUniversalTime(),               // write
        v => DateTime.SpecifyKind(v, DateTimeKind.Utc)); // read
```

Apply globally for all `DateTime` columns mapped to `timestamptz`:

```csharp
foreach (var entity in modelBuilder.Model.GetEntityTypes())
foreach (var prop in entity.GetProperties())
{
    if (prop.ClrType == typeof(DateTime) || prop.ClrType == typeof(DateTime?))
    {
        prop.SetValueConverter(new ValueConverter<DateTime, DateTime>(
            v => v.ToUniversalTime(),
            v => DateTime.SpecifyKind(v, DateTimeKind.Utc)));
    }
}
```

### Write path — normalize before Save

At the boundary (DTO → entity, or in an interceptor):

```csharp
user.CreatedAt = user.CreatedAt.Kind switch
{
    DateTimeKind.Utc         => user.CreatedAt,
    DateTimeKind.Local       => user.CreatedAt.ToUniversalTime(),
    DateTimeKind.Unspecified => DateTime.SpecifyKind(user.CreatedAt, DateTimeKind.Utc),
    _                        => throw new InvalidOperationException()
};
```

Prefer `DateTimeOffset` for new columns — it forces the caller to
commit to an offset and removes the whole class of bug.

### Emergency opt-out (last resort)

```csharp
AppContext.SetSwitch("Npgsql.EnableLegacyTimestampBehavior", true);
```

This restores pre-6.0 behavior for the whole process. **Don't ship
this.** It's a triage tool to keep a production app alive while you
apply the real fixes above. Remove it in the same PR that lands the
value converter.

## Related

- `rules/dotnet/npgsql.md` — canonical rule; this runbook restates
  the symptom-first variant.
- `rules/postgres/migrations.md` — always prefer `timestamptz` over
  `timestamp` for new columns.
- `.claude/agents/dotnet-dev.md` — specialist invoked when this
  symptom appears during a .NET build/test step.
- `.claude/agents/sql-specialist.md` — owns migration review; will
  flag unsafe `timestamp` → `timestamptz` conversions.
