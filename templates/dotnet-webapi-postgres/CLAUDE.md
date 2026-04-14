# Project rules (dotnet-webapi-postgres)

Scaffolded from the soup `dotnet-webapi-postgres` template. The parent
`CLAUDE.md` + `CONSTITUTION.md` iron laws apply. Additional project rules:

## Stack

- **Runtime:** .NET 8, ASP.NET Core Web API
- **DB:** Postgres 16 via EF Core + Npgsql
- **Tests:** xUnit + `WebApplicationFactory` + Testcontainers Postgres (default)

## Layout

```
Program.cs            Host + routing
Controllers/          API controllers
Models/               DTOs (records)
Data/                 DbContext + entities
Migrations/           EF Core migrations (seeded initial migration included)
YourApi.Tests/        xUnit integration tests (PostgresFixture)
YourApi.sln           Solution file (required for multi-project worktrees)
.editorconfig         Formatting rules; `dotnet format --verify-no-changes` in CI
.config/
  dotnet-tools.json   dotnet-ef pinned to 8.0.8
```

## Rules for agents

1. **Nullable reference types enabled**; address all warnings. Warnings are errors (`TreatWarningsAsErrors=true`).
2. **XML doc comments on every public type/member**. Controllers are covered
   by the project-wide `CS1591` suppression — add docs where they help.
3. **Controllers stay thin.** Business logic goes in services. DI registers them in `Program.cs`.
4. **All DB access via `AppDbContext`.** No raw `NpgsqlConnection`. No direct SQL in controllers.
5. **Integration tests use `PostgresFixture`** (Testcontainers). The InMemory
   path is behind `USE_INMEMORY` — use it only when Docker is unavailable.
6. **Connection strings come from `ConnectionStrings:Postgres`** in config;
   env override via `ConnectionStrings__Postgres`. No hardcoded fallback.

## `dotnet ef` workflow

Adding a schema change is a **two-role** operation (Constitution V):

1. **dotnet-dev** adds or modifies the entity + `AppDbContext` configuration.
2. **dotnet-dev** runs `dotnet ef migrations add <Name>` (or the wrapper:
   `python -m cli_wrappers.dotnet ef-migrate <Name>`). This generates:
   - `Migrations/<timestamp>_<Name>.cs` (forward/back C# bodies)
   - `Migrations/<timestamp>_<Name>.Designer.cs`
   - `Migrations/AppDbContextModelSnapshot.cs` (regenerated)
3. **dotnet-dev** generates the raw SQL pair for review:
   ```bash
   python -m cli_wrappers.dotnet ef-script \
       --output Migrations/<timestamp>_<Name>.up.sql
   python -m cli_wrappers.dotnet ef-script --from <Name> --to <previous> \
       --output Migrations/<timestamp>_<Name>.down.sql
   ```
4. **dotnet-dev** hands the `.sql` pair + the `.cs` changes + the
   `ModelSnapshot.cs` diff to **sql-specialist** for review.
5. **sql-specialist** reviews the `Up()` / `Down()` method bodies and the
   `.sql` pair, applies any Postgres-specific adjustments (e.g.
   `CONCURRENTLY` via `migrationBuilder.Sql(..., suppressTransaction: true)`,
   `timestamptz` columns, `NULLS NOT DISTINCT` on unique indexes), and
   commits.
6. Apply with `just ef-update` or `python -m cli_wrappers.dotnet ef-update`.

### When to call sql-specialist

- Any change that touches `**/Migrations/**` or `**/*.sql`.
- Index additions on large tables (need `CONCURRENTLY`).
- New unique indexes where `NULL` semantics matter.
- Anything involving `timestamptz`, `jsonb`, custom types, triggers, RLS,
  partial/expression indexes.

## Local dev

```bash
just build
just test          # Testcontainers Postgres — needs Docker running
just up            # docker compose: db, migrate, api on :8080
```
