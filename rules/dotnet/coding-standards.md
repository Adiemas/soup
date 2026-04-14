# .NET — coding standards

Target: .NET 8 LTS, C# 12. Preferred stack: ASP.NET Core Web API + EF Core + xUnit + FluentAssertions.

## 1. Project settings

Every `.csproj` MUST set:

```xml
<PropertyGroup>
  <TargetFramework>net8.0</TargetFramework>
  <LangVersion>12.0</LangVersion>
  <Nullable>enable</Nullable>
  <ImplicitUsings>enable</ImplicitUsings>
  <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
  <AnalysisLevel>latest-recommended</AnalysisLevel>
  <EnforceCodeStyleInBuild>true</EnforceCodeStyleInBuild>
</PropertyGroup>
```

Solution-wide: a `.editorconfig` pins formatting; `dotnet format --verify-no-changes` is part of CI.

### 1.1 `TreatWarningsAsErrors` × `CS1591`

`TreatWarningsAsErrors=true` combined with `<GenerateDocumentationFile>true</GenerateDocumentationFile>`
turns missing-XML-doc (`CS1591`) into a build-breaking error. Controllers are
framework plumbing and often don't benefit from per-action XML docs. Add a
project-wide suppression:

```xml
<NoWarn>$(NoWarn);CS1591</NoWarn>
```

This keeps the XML doc requirement where it matters (domain/services/options)
without fighting boilerplate. Prefer the project-wide suppression over
per-file `#pragma warning disable`.

## 2. Nullable reference types

1. Nullable is always enabled. No `#nullable disable`.
2. Annotate intent: `string?` means "may be null"; `string` means "never null."
3. Never use `!` (null-forgiving) to silence a warning without a preceding runtime check or contract.
4. Guard arguments at public boundaries: `ArgumentNullException.ThrowIfNull(invoice)` (or the nameof-aware `ArgumentException.ThrowIfNullOrWhiteSpace`).

## 3. Async/await

1. All I/O is `async Task` / `async Task<T>`. No blocking on async code (`.Result`, `.Wait()`, `.GetAwaiter().GetResult()`) — deadlock risk.
2. Method names that return Tasks end with `Async`: `GetInvoiceAsync`.
3. Every async chain accepts a `CancellationToken ct = default` and flows it through.
4. Use `ConfigureAwait(false)` in library code; in ASP.NET Core application code it's optional (no sync context).
5. Prefer `await using` for `IAsyncDisposable`.

```csharp
public async Task<Invoice> GetInvoiceAsync(Guid id, CancellationToken ct = default)
{
    var invoice = await _db.Invoices.FindAsync(new object[] { id }, ct).ConfigureAwait(false);
    return invoice ?? throw new InvoiceNotFoundException(id);
}
```

## 4. Dependency injection

1. Composition root lives in `Program.cs`. No `new` of services anywhere else.
2. Constructors are the only injection point. No property injection. No service locator.
3. Register with correct lifetimes:
   - `AddSingleton` — stateless, thread-safe (options, factories).
   - `AddScoped` — per-request state (DbContext, unit of work).
   - `AddTransient` — cheap, stateless, short-lived.
4. Options pattern for config: `builder.Services.Configure<InvoicesOptions>(config.GetSection("Invoices"))`.
5. Never inject `IServiceProvider` into application code; it's a smell.

## 4a. Model validation & `[ApiController]`

Controllers decorated with `[ApiController]` get **automatic 400** responses
on invalid model state — the framework short-circuits the action **before** it
runs. Consequences:

1. Manual `if (!ModelState.IsValid) return BadRequest(...)` checks are
   redundant. Delete them.
2. Null body on `[FromBody]` parameters triggers the auto-400 too; any
   `BadRequest` branch you wrote for "null body" **will never execute**.
3. FluentValidation integration is the canonical replacement for manual
   `ModelState` checks: `services.AddFluentValidationAutoValidation()` wires
   validators into the same pipeline.
4. Opt-out (rare, e.g. custom problem+json shape) via:
   ```csharp
   services.Configure<ApiBehaviorOptions>(o => o.SuppressModelStateInvalidFilter = true);
   ```
   Do this only with an architect sign-off; it removes a guardrail the whole
   team relies on.

## 5. EF Core

1. Each bounded context has **one** `DbContext`. Register as scoped.
2. Migrations: `dotnet ef migrations add <Name>`. Every migration is reviewed and committed; we check in the `Migrations/` folder.
3. No lazy loading. Prefer explicit `.Include(...)` / `.ThenInclude(...)`.
4. Read queries use `AsNoTracking()`.
5. Never call `SaveChanges` inside a loop — batch or reshape.
6. Model configuration lives in `IEntityTypeConfiguration<T>` classes, one per entity.

```csharp
public sealed class InvoiceConfiguration : IEntityTypeConfiguration<Invoice>
{
    public void Configure(EntityTypeBuilder<Invoice> b)
    {
        b.HasKey(i => i.Id);
        b.Property(i => i.TotalCents).IsRequired();
        b.HasIndex(i => i.CustomerId);
    }
}
```

### 5.1 Npgsql 6+ UTC-only (timestamp/tz landmine)

Npgsql 6+ enforces **UTC-only** writes to `timestamp with time zone`
(`timestamptz`). A `DateTime` whose `Kind` is `Unspecified` or `Local` throws at
`SaveChanges`. Rules:

1. All `DateTime` values written to Postgres **must** have `Kind == DateTimeKind.Utc`.
   Construct via `DateTime.UtcNow`, `DateTime.SpecifyKind(x, DateTimeKind.Utc)`,
   or read back from the DB where the provider sets the kind.
2. Prefer `DateTimeOffset` on public-facing APIs and DTOs — it carries the
   offset explicitly and removes the "kind confusion" class of bugs entirely.
3. **Do not** re-enable the legacy behavior:
   ```csharp
   // BANNED — we want the UTC enforcement.
   AppContext.SetSwitch("Npgsql.EnableLegacyTimestampBehavior", true);
   ```
   If you find this flag set, that's a red flag — rewrite the callsites to
   use `Utc`.
4. Schema side: `timestamptz` always. Never `timestamp without time zone`.
   See `rules/postgres/migrations.md §7` and `rules/dotnet/npgsql.md`.

## 6. Error handling

1. Define domain exceptions in the core, e.g. `InvoiceAlreadyPaidException : Exception`.
2. Map exceptions to HTTP at a central middleware, not in controllers.
3. Controllers return `ActionResult<T>` with typed results (`TypedResults.Ok(...)`, `TypedResults.NotFound()`).
4. Never catch `Exception` without re-throwing or translating. Never catch `Exception` and log only.

## 7. Records & immutability

1. Prefer `record` / `record struct` for DTOs and value types. They get value equality + `with` expressions for free.
2. Use `init`-only setters for invariants that must be set at construction.
3. Collections on records are `IReadOnlyList<T>` — not `List<T>`.

## 8. Naming

1. PascalCase for types, methods, properties, constants. camelCase for locals and parameters. `_camelCase` for private fields.
2. Interfaces start with `I`: `IInvoiceRepository`.
3. Async methods end in `Async`.
4. Don't abbreviate: `InvoiceRepository`, not `InvRepo`.

## 9. Formatting

1. `dotnet format` is the source of truth. CI enforces.
2. File-scoped namespaces (`namespace Soup.Invoices;`). No block namespaces.
3. One public type per file, file name = type name.
4. `using` directives outside the namespace, System first, then others, then statics, separated by blank lines — handled by `dotnet format`.

## 10. Logging

1. Use `ILogger<T>` via DI. No `Console.WriteLine`.
2. Structured logging with message templates: `_log.LogInformation("Paid invoice {InvoiceId} amount {Cents}", id, cents);` — never string-interpolate templates.
3. Correlation IDs flow through `Activity.Current` (OpenTelemetry).

## 11. Checklist before commit

- [ ] `dotnet build` clean (warnings as errors)
- [ ] `dotnet format --verify-no-changes`
- [ ] `dotnet test` green
- [ ] All new public APIs have XML doc comments
- [ ] No `!` null-forgiving without a guarded context
- [ ] No sync-over-async, no `.Result`
