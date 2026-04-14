# YourApi — ASP.NET Core 8 + Postgres

Scaffolded from the soup `dotnet-webapi-postgres` template.

## Quick start

```bash
just up
curl http://localhost:8080/Health
```

## Tests

```bash
just test
```

Tests run against EF Core InMemory; no live Postgres required.

## Migrations

```bash
just ef-migrate Init
just ef-update
```

## Layout

See `CLAUDE.md` for the agent contract.
