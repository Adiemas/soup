# Migrations

This template ships with an initial EF Core migration
(`20260101000000_InitialCreate`) plus matching Designer/ModelSnapshot so a
fresh clone can run `just ef-update` without authoring anything.

Workflow:

```bash
# Apply all pending migrations against the configured Postgres instance.
just ef-update

# Create a new migration after modifying entities/AppDbContext.
just ef-migrate AddCustomers
# Review the generated .cs + Designer.cs + ModelSnapshot.cs diff.
# Generate the raw SQL for sql-specialist review/commit:
python -m cli_wrappers.dotnet ef-script --output Migrations/20YYMMDDHHMMSS_AddCustomers.up.sql
python -m cli_wrappers.dotnet ef-script --from AddCustomers --to <previous> \
    --output Migrations/20YYMMDDHHMMSS_AddCustomers.down.sql
```

Ownership (Constitution V):

- `sql-specialist` authors the `.up.sql` / `.down.sql` pair and reviews the
  `Up()` / `Down()` bodies in the generated C# migration class.
- `dotnet-dev` owns the C# scaffolding (`.cs`, `.Designer.cs`) and the
  `AppDbContextModelSnapshot.cs` diff, but commits only after sql-specialist
  signs off.

Never hand-edit an applied migration; create a new one.

