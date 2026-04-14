# Cycle 2 — .NET/C# Path Readiness Critic

Independent review. Scope: .NET + Postgres path only. Date: 2026-04-14.

Artifacts read: `.claude/agents/dotnet-dev.md`, `.claude/agents/sql-specialist.md`, `rules/dotnet/coding-standards.md`, `rules/dotnet/testing.md`, `rules/postgres/migrations.md`, `templates/dotnet-webapi-postgres/*`, `cli_wrappers/dotnet.py`, `.claude/commands/{plan,tasks,implement}.md`, `library.yaml`. Mock app `mock-apps/asset-tracker/` was **not present** at time of review (only `prompt-library/` exists under `mock-apps/`).

## Frontend/backend stack audit

### 1. `dotnet-dev` agent (`.claude/agents/dotnet-dev.md`)

- Patch B routing to `sql-specialist` **is in place** — line 38 explicitly lists "EF migrations authored here — hand off to `sql-specialist`" as a red-flag violation. Good.
- However the card does **not** tell the agent *how* to hand off (no prompt template, no invocation command, no "emit TaskStep for sql-specialist" guidance). Compare with the specificity in sql-specialist.md line 24 ("If EF Core, update model snapshot"). Handoff contract is underspecified — one-way expectation with no round-trip.
- Process (lines 21-25) mandates RED→GREEN, but lists no step for `dotnet restore` nor `dotnet ef migrations script` preview before handoff. Running `dotnet test --filter` on a fresh worktree (Constitution III worktrees) will fail without restore.
- No guidance on EF Core **vs raw ADO.NET / Npgsql direct**. The card is silent on when Dapper or `NpgsqlDataSource` would be acceptable (e.g., for high-throughput read paths, bulk copy, LISTEN/NOTIFY). Template CLAUDE.md line 28 bans "raw `NpgsqlConnection`" outright — the dev-agent card does not echo this, creating a known-unknown contract conflict.
- Model is `sonnet` (line 5) — reasonable; orchestrator can escalate.
- No mention of `dotnet format --verify-no-changes` as part of Process, though `rules/dotnet/coding-standards.md:100,114` mandates it. Agent will likely run `dotnet format` (line 24) but not verify clean tree.

### 2. `sql-specialist` for Postgres (`.claude/agents/sql-specialist.md`)

- Half-generic / half-PG. Line 13 says "PostgreSQL 16" + tooling, but **red-flags list (lines 35-40) is DB-agnostic** — no mention of `CONCURRENTLY`, `NULLS NOT DISTINCT`, partial/expression indexes, or `timestamptz` vs `timestamp`.
- `CONCURRENTLY` **is mentioned once in Iron laws line 33** ("concurrent where possible") but the *non-transactional* consequence (Alembic `transactional_ddl=False`, EF `suppressTransaction: true`) is absent from the agent card (though present in `rules/postgres/migrations.md:52`).
- No coverage of EF Core specifics that sql-specialist must know: `__EFMigrationsHistory` table, `migrationBuilder.Sql("...", suppressTransaction: true)`, how to author the matching `Down()` method in the EF C# migration class, and how EF model snapshot (`ModelSnapshot.cs`) regenerates. Line 25 says "update model snapshot" but doesn't say how (`dotnet ef migrations add` is the only path — and that step lives in `dotnet-dev`'s wrapper).
- No guidance on partial indexes (`WHERE deleted_at IS NULL`), expression indexes, or trigger/function patterns (`LANGUAGE plpgsql`), no test-with-pgtap. Triggers mentioned only as a red-flag (line 37 "without tests") — no pointer to a pattern.
- Role conflict: sql-specialist is declared "sole author" (line 3) but the EF migration class is a `.cs` file that `dotnet-dev` owns by file-type. Boundary undefined — who edits `Migrations/*.Designer.cs` if dotnet-dev only owns `.cs/.csproj/.sln` (dotnet-dev.md line 3)? This is a **latent ownership bug**.

### 3. Rules coverage — missing topics for .NET+Postgres prod

| Topic | Present? | Evidence |
|---|---|---|
| Nullable ref type basics | Yes | `coding-standards.md:22-28` |
| Nullable edge cases w/ EF Core (nav properties, `null!` initializer, `required` members) | **Missing** | no section in coding-standards §5 |
| Npgsql vs other drivers (Dapper, Microsoft.Data.Sqlite) | **Missing** | no mention in any rules file |
| `NpgsqlDataSource` / connection pooling / `MaxPoolSize` / `KeepAlive` | **Missing** | neither rule file mentions it |
| DI lifetimes Singleton/Scoped/Transient | Partial | `coding-standards.md:50-54` lists rules but does not warn about captured dependencies (Scoped-in-Singleton), `IHttpContextAccessor` caveat, or `IHttpClientFactory` |
| Async all the way down | Yes | `coding-standards.md:31-36` |
| xUnit mandated? | Implied | `testing.md:1,3` says "Tool: xUnit" — but never says "no NUnit/MSTest allowed" explicitly; constitution not cited |
| FluentAssertions patterns | Yes | `testing.md:59-65` |
| Unit vs integration split | Partial | `testing.md:7-16` shows layout; line 102-106 mandates Testcontainers — good, but Program template README.md:18 contradicts: "Tests run against EF Core InMemory" |
| Testcontainers for Postgres | Mentioned | `testing.md:104` (`Testcontainers (Postgres, Redis)`) but no example, no wiring, and template YourApi.Tests uses InMemory |

Additional gaps in `rules/dotnet/testing.md`:
- No guidance on `TimeProvider` (abstract time) — a .NET 8 native primitive used in clean tests.
- No guidance on `IClassFixture` vs `ICollectionFixture` vs `IAsyncLifetime` — relevant for Testcontainer setup.
- FluentAssertions v8 licensing change (Apr 2025) not flagged. Production projects now often pin to v7 or migrate to Shouldly; rules pin nothing (no version, no license note).

Gaps in `rules/postgres/migrations.md`:
- EF Core `suppressTransaction` is mentioned (line 52) — good. But no example showing the paired C# migration `Up()`/`Down()` plus `migrationBuilder.Sql(@"CREATE INDEX CONCURRENTLY...", suppressTransaction: true)`.
- No discussion of `EnableRetryOnFailure` with migrations (it breaks transactional migrations — known Npgsql EF Core pitfall).
- Line 45-46 says EF Core must "use raw SQL for CONCURRENTLY" but does not show `MigrationBuilder.Sql(..., suppressTransaction: true)` nor mention the `IMigrationsSqlGenerator` override route.

### 4. Template `templates/dotnet-webapi-postgres/`

- **Minimally runnable?** Partially.
- `YourApi.csproj` (lines 1-25) is complete enough to `dotnet restore` + build. But it is **missing**: `<LangVersion>12.0</LangVersion>` (mandated by `coding-standards.md:13`), `<AnalysisLevel>latest-recommended</AnalysisLevel>` (coding-standards:16), `<EnforceCodeStyleInBuild>true</EnforceCodeStyleInBuild>` (coding-standards:17), `coverlet.collector` (testing.md:122). These are explicit "MUST" items — template non-compliant.
- No `.editorconfig` at template root — coding-standards.md:21 says "a `.editorconfig` pins formatting; `dotnet format --verify-no-changes` is part of CI". Template will fail that CI check on first run.
- No `YourApi.sln` solution file. `.claude/commands/plan.md` and `tasks.md` expect `dotnet` projects but offer no scaffolding step. `dotnet test` and `dotnet build` work without a sln at repo root only because the template has a single csproj; adding a second project (test project is separate) requires a `.sln` to avoid ambiguous resolution. There is a csproj in `YourApi.Tests/` but no sln linking the two.
- Are **EF migrations provided**? No — `Migrations/README.md` says "Generated by `dotnet ef migrations add <Name>`" (lines 3-4). `AppDbContext` declares `DbSet<AppMeta>` (line 12) but there is **no initial migration**. First `dotnet ef database update` will fail because there is nothing to apply. HealthController.cs:25 does `_db.Database.CanConnectAsync()` which succeeds against empty Postgres — so the happy path works, but a true schema round-trip does not.
- `docker-compose.yml` stands up Postgres + API (lines 2-28). Postgres healthcheck good. API depends_on `service_healthy`. **Issue:** no migration step runs between container start and API serving — app starts against empty schema. Dockerfile (lines 6-7) also `COPY . .` after `COPY YourApi.csproj ./`, which copies the **test project** into the build context; `dotnet publish YourApi.csproj` will still work, but the test project's csproj is shipped into the container image (bloat + SDK leak).
- `HealthControllerTests.cs:26` uses `UseInMemoryDatabase("tests")` — **this contradicts** `rules/dotnet/testing.md:102-106` and `rules/postgres/migrations.md:81` (Testcontainers in CI). The InMemory provider is known to mis-emulate Npgsql (case sensitivity, JSON ops, tsvector, concurrency tokens). The template teaches the wrong pattern.
- `Program.cs:23,26` mixes controllers and MapGet inline — style-OK but line 11-13 falls back to a hard-coded default connection string, bypassing the "no magic strings for config" red-flag in dotnet-dev.md:39. Should fail fast if not set.
- `Program.cs` has no `/health` middleware (`AddHealthChecks`), no logging config, no `UseSerilog`/OpenTelemetry wiring. Coding-standards §10:107-110 mandates ILogger + correlation via Activity, but no OTel package in csproj.

### 5. CLI wrapper `cli_wrappers/dotnet.py`

- Covers: `build`, `test` (with TRX parsing — nice), `run`, `pack`, `ef-migrate`, `ef-update`. Good core.
- **Missing dotnet ef subcommands:** `ef migrations remove`, `ef migrations list`, `ef migrations script [--idempotent]`, `ef dbcontext info`, `ef dbcontext scaffold`. Production teams regularly ship via idempotent scripts (`ef migrations script --idempotent -o migrate.sql`); no wrapper surface.
- **Missing `dotnet format`** — neither `dotnet format`, `dotnet format --verify-no-changes`, nor `dotnet format analyzers`/`style`/`whitespace` sub-targets. Constitution-level check (coding-standards.md:100) with no wrapper.
- **Missing `dotnet tool restore` + `dotnet-reportgenerator-globaltool`** — coverage threshold (testing.md:122-124) has no execution path to produce/enforce the HTML or Cobertura report.
- No wrapper for **Roslyn analyzers** specifically; they're implicit via `dotnet build`, but no knob to escalate/silence. No `dotnet list package --vulnerable`, no `dotnet list package --outdated` — supply-chain blind spot.
- Timeouts: `build_cmd` uses 1200 s default (line 24, 45), `test_cmd` 1800 (line 114). Fine for CI; `run_cmd` has 600 s which is too short for long-running debug sessions but acceptable for "short-lived commands" as docstring claims.
- No `--configuration Release` default on `test` (InMemory tests will pass Debug-only pitfalls).

### 6. Spec-driven flow for .NET

- `/plan` (lines 16-22) routes to `architect` then `plan-writer`; the latter emits markdown with `## File map`. Template `dotnet-webapi-postgres/` has project files at root (Program.cs, Controllers/, etc.) — no `src/` layout as the coding-standards.md:15 and testing.md:7-14 prescribe (`src/<Project>/`, `tests/<Project>.Tests/`). The template and rules are **at odds**, so plan-writer will emit conflicting file maps depending on which it anchors on.
- `/tasks` (lines 17-22) mandates test-step-before-impl-step. For .NET this maps cleanly to xUnit `[Fact]` RED cycle. However `tasks-writer` has no awareness of the "sql-specialist authors EF migrations" boundary — if a task touches `Migrations/`, no auto-injection routes to sql-specialist. Patch B updated the dotnet-dev agent card; `tasks-writer` routing logic is **not** demonstrated to pick this up.
- `/implement` (lines 17-22) spawns per-step subagents in worktrees with `files_allowed`. For .NET: cross-project builds need the solution file. `files_allowed` on a subagent touching `YourApi.csproj` will NOT cover `YourApi.Tests.csproj` unless globbed explicitly. Combined with the missing `.sln`, this creates friction — the subagent may not be able to compile its dependency graph.

## Concrete gap list

| File | Gap | Evidence | Fix |
|---|---|---|---|
| `.claude/agents/dotnet-dev.md` | No handoff contract to sql-specialist | line 38 (flag) vs no procedure | Add step: "If task touches schema, emit follow-up TaskStep `agent: sql-specialist`, wait for its commit, then run `dotnet ef migrations add` locally." |
| `.claude/agents/dotnet-dev.md` | Silent on Dapper/Npgsql direct use | lines 12-13 mention only EF Core | Add "Allowed data access: EF Core (default); `NpgsqlDataSource` only for bulk copy or LISTEN/NOTIFY with architect sign-off." |
| `.claude/agents/sql-specialist.md` | Not truly PG-specific | lines 35-40 generic | Add red-flags: non-`timestamptz` timestamps, FK without `ON DELETE`, missing `CONCURRENTLY`, missing `IF NOT EXISTS`/`NULLS NOT DISTINCT` where needed |
| `.claude/agents/sql-specialist.md` | No EF Core authoring guidance | line 25 one-liner | Add example with `migrationBuilder.Sql(@"...", suppressTransaction: true)` and reference to `ModelSnapshot.cs` regeneration |
| `.claude/agents/sql-specialist.md` | Ownership overlap with dotnet-dev on `.cs` migrations | agent cards disagree | Scope sql-specialist to `Migrations/*.cs` + `*.Designer.cs` + `ModelSnapshot.cs`; dotnet-dev owns rest |
| `rules/dotnet/coding-standards.md` | No Npgsql / pooling / `NpgsqlDataSource` section | §5 EF Core only (lines 58-76) | Add §5b: pooling defaults, `MaxPoolSize`, `Timeout`, `KeepAlive`, `NpgsqlDataSource` registration |
| `rules/dotnet/coding-standards.md` | No DI lifetime trap guidance | lines 50-55 | Add "captured-dependency" rule: Scoped inside Singleton is a bug; use `IServiceScopeFactory` |
| `rules/dotnet/coding-standards.md` | Nullable + EF edges missing | §2 (22-28), §5 (58-76) separate | Add: `required` members on entities, `null!` initializer pattern, `[NotMapped]` + nullable nav property |
| `rules/dotnet/testing.md` | No explicit "xUnit mandated" statement | line 3 "Tool: xUnit" | State: "NUnit and MSTest are prohibited." |
| `rules/dotnet/testing.md` | No FluentAssertions version/license note | §4 (59-65) | Pin version or switch to Shouldly; note license change |
| `rules/dotnet/testing.md` | Testcontainers lacks concrete wiring | line 104 one-liner | Add snippet with `IAsyncLifetime`, `PostgreSqlContainer`, `WebApplicationFactory<Program>.WithPostgres()` extension |
| `rules/postgres/migrations.md` | No EF Core `suppressTransaction` example | line 46, 52 | Add Up()/Down() C# snippet |
| `templates/.../YourApi.csproj` | Missing mandated props | coding-standards §1 | Add `LangVersion`, `AnalysisLevel`, `EnforceCodeStyleInBuild` |
| `templates/.../YourApi.csproj` | No `coverlet.collector` | testing.md:122 | Add PackageReference in YourApi.Tests.csproj |
| `templates/.../` | No `.editorconfig` | coding-standards.md:21 | Ship one aligned with `dotnet format` defaults |
| `templates/.../` | No `YourApi.sln` | plan-writer/orchestrator worktrees | `dotnet new sln -n YourApi && dotnet sln add` both projects |
| `templates/.../HealthControllerTests.cs` | Uses InMemory, contradicts rules | line 26 vs testing.md:104 | Replace with Testcontainers + `PostgreSqlContainer` |
| `templates/.../Program.cs` | Hardcoded fallback connection string | lines 11-13 | Remove fallback; `throw` on missing config |
| `templates/.../` | No initial EF migration | Migrations/README.md only | Check in an `InitialCreate` migration so `just up && just ef-update` works cold |
| `templates/.../Dockerfile` | Copies test project into image | line 6 `COPY . .` | Use `.dockerignore` or multi-stage that copies only `YourApi/` |
| `templates/.../docker-compose.yml` | No migration step between db-ready and api-start | lines 18-27 | Add a one-shot `migrate` service using `dotnet ef database update` or a generated idempotent SQL |
| `cli_wrappers/dotnet.py` | No `dotnet format` wrapper | file scan | Add `format` subcommand with `--verify-no-changes` flag |
| `cli_wrappers/dotnet.py` | No `ef migrations script --idempotent` | lines 196-238 | Add `ef-script` subcommand for prod deploys |
| `cli_wrappers/dotnet.py` | No `ef migrations remove` | ibid | Add `ef-remove` subcommand |
| `cli_wrappers/dotnet.py` | No supply-chain inspection | file | Add `list-packages --vulnerable / --outdated` |
| `.claude/commands/tasks.md` | No stack-aware routing for .NET migrations | lines 15-23 | Instruct tasks-writer: "If step touches `**/Migrations/**` or `**/*Context.cs`, set `agent: sql-specialist`" |

## Top 10 ranked actionable fixes

1. **Replace InMemory with Testcontainers in the template tests** (`HealthControllerTests.cs:26` → Postgres container) — single biggest correctness lie; everything downstream assumes this.
2. **Add an initial EF Core migration** to the template so `just up` → `just ef-update` works cold; today it requires manual `ef migrations add` before anything does.
3. **Fix `YourApi.csproj`**: add `LangVersion=12.0`, `AnalysisLevel=latest-recommended`, `EnforceCodeStyleInBuild=true`; add `coverlet.collector` to test csproj; add `.editorconfig`. Rules already mandate this — template fails its own contract.
4. **Extend `cli_wrappers/dotnet.py`** with `format` (and `format --verify-no-changes`) + `ef-script --idempotent` — both are blockers for CI.
5. **Tighten `sql-specialist.md`** with PG-specific red-flags (no `timestamptz`, missing `ON DELETE`, absent `CONCURRENTLY`) and an EF Core `suppressTransaction: true` example.
6. **Resolve ownership conflict**: sql-specialist explicitly owns `Migrations/**/*.cs`, `ModelSnapshot.cs`, `*.Designer.cs`; dotnet-dev owns all other `.cs`. Update both cards and `tasks-writer` routing.
7. **Add solution file (`YourApi.sln`)** to the template — required for multi-project worktree subagents under `/implement`.
8. **Add a migration-run step in `docker-compose.yml`** (one-shot init container) so the stack is truly end-to-end from cold.
9. **Remove hardcoded fallback connection string from `Program.cs` lines 11-13**; fail fast on missing `ConnectionStrings:Postgres`. Matches dotnet-dev.md:39 "magic strings" red flag.
10. **Rules: add Npgsql/`NpgsqlDataSource`/pooling section + DI lifetime traps** to `rules/dotnet/coding-standards.md`. These two omissions are the highest-leverage prod issues for .NET + Postgres.

## Residual concerns (known-unknowns)

- **`mock-apps/asset-tracker/` is absent** at review time; could not validate end-to-end dogfooding. If the builder agent is still writing it, a follow-up pass is required to confirm: does the template actually produce a working asset-tracker? Does `just test` go green with Testcontainers?
- **FluentAssertions v8 licensing** (Apr 2025): rules are silent. Team must decide: pin v7, buy a license, or migrate to `Shouldly` / `AwesomeAssertions`. Unresolved.
- **Windows-specific CRLF / path issues** on `dotnet format` and bash-shebang justfile (`set shell := ["bash", "-cu"]` line 1 of justfile) — unverified on Windows-hosted dev loops.
- **Whether `tasks-writer`'s library.yaml lookup can distinguish migration tasks** and auto-route to sql-specialist was not directly tested (no JSON plan example for .NET stack in `.soup/plans/`).
- **OpenTelemetry / correlation**: coding-standards §10 mentions `Activity.Current` but no OTel packages in csproj; unclear if this is intentional (opt-in later) or a gap.
- **`dotnet ef` bundles (`dotnet ef migrations bundle`)** — zero-tool prod deploy story. No mention anywhere. Known-unknown on prod ops.
- **No `global.json`** pinning SDK version at template root — contributors on 8.0.200 vs 8.0.400 may diverge on analyzer behavior.
- **Constitution Article V claims sql-specialist is "sole author"** of migrations but that constitution file was not re-read in this pass; the agent card (`sql-specialist.md:3`) cites V but the current V.x numbering (III.5, V.1, V.2, V.3) is only quoted — consistency with live CONSTITUTION.md deferred.

---

Word count ~1780.
