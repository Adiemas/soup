# FEEDBACK — Streck Asset Tracker (.NET path dogfood, 2026-04-14)

Walked `/specify → /clarify → /plan → /tasks → /implement → /verify` for ASP.NET Core 8 + EF Core + Postgres. Excludes items already logged in `mock-apps/prompt-library/FEEDBACK.md`.

## 1. .NET-specific friction

1. **`cli_wrappers/dotnet.py` has no `ef-script`, `ef-remove`, or `format`.** Without `dotnet ef migrations script --from X --to Y`, `sql-specialist` cannot emit direction-specific SQL for the `.down.sql` companion Constitution V.1 mandates. I hand-authored both `mock-apps/asset-tracker/src/Streck.AssetTracker/Migrations/20260414120000_Init{,.down}.sql`.
2. **TRX parser is namespace-brittle.** `_parse_trx` pins xUnit v2's TRX namespace; v3 or alternative loggers yield empty `counts`, which the wrapper still reports as `status: ok`. Silent "green" on a null suite.
3. **`TreatWarningsAsErrors=true` + `GenerateDocumentationFile=true`** kills the `partial class Program` marker required by `WebApplicationFactory<Program>` unless `<NoWarn>$(NoWarn);CS1591</NoWarn>` is added. Template hides this; `rules/dotnet/coding-standards.md §1` doesn't mention CS1591.
4. **Npgsql 6+ UTC-only writes are undocumented.** `timestamptz` throws without `AppContext.SetSwitch("Npgsql.EnableLegacyTimestampBehavior", false)` + `DateTime.SpecifyKind(..., Utc)` at every boundary. Not in `rules/dotnet/coding-standards.md §5` or `rules/postgres/migrations.md §7.4`.
5. **`EF Core InMemory` doesn't enforce FKs**, so spec REQ-9 (FK violation → 422) can't be exercised with the template's default test stack. That contradicts `rules/dotnet/testing.md §7.2` (Testcontainers). Template wins by inertia.
6. **`[ApiController]` auto-400 short-circuits actions.** Framework returns 400 on null body before the handler runs — any BadRequest code path I wrote for null never executes. Not called out in `rules/dotnet/coding-standards.md §6`.
7. **"No service locator" iron law** (dotnet-dev.md) reads as if it bans `services.Single(...) + services.Remove(...)` — the canonical test pattern for swapping `DbContextOptions`. Add "in production code" qualifier.

## 2. Rule coverage gaps

`rules/dotnet/coding-standards.md §5` omits Npgsql UTC, `DeleteBehavior` defaults, UUID v7 vs `gen_random_uuid()`, `[ApiController]` semantics. `rules/dotnet/testing.md §7` never mentions `WebApplicationFactory<T>` or the `partial class Program` marker. `rules/postgres/migrations.md §2` shows only Alembic — needs `§2.4 EF Core: authoring the .down.sql via dotnet ef migrations script`.

## 3. sql-specialist ↔ dotnet-dev handoff

Constitution V.4 says `sql-specialist` is sole migration author; in EF Core the `Migrations/` folder holds raw `.sql` (sql-specialist) **and** scaffolded C# migration classes (dotnet-dev — it's C#). No rule assigns ownership of the C# class. I split: S3 `sql-specialist` (raw `.sql` only), S4 `dotnet-dev` (DbContext + configs). Add `rules/postgres/migrations.md §1.4`: "C# migration class is co-owned; sql-specialist reviews. Raw `.sql`/`.down.sql` are sql-specialist-exclusive." There's also no `TaskStep.reviewed_by` to express the handoff in `ExecutionPlan`.

## 4. Template gaps (`templates/dotnet-webapi-postgres/`)

- No `FluentAssertions` or `coverlet.collector` in `YourApi.Tests.csproj` (rules §4, §10 demand both).
- No `.editorconfig` (rule §1 promises).
- Flat layout (`YourApi/` + `YourApi.Tests/`) — `rules/dotnet/testing.md §1` requires `src/` + `tests/`. I used the rule's layout.
- No API healthcheck in `docker-compose.yml`; added one in mine.
- `[Route("[controller]")]` yields PascalCase `/Health` — no rule enforces kebab-case; I used explicit `[Route("health")]`.

## 5. Tool gaps — `cli_wrappers/dotnet.py`

Missing: `ef-script`, `ef-remove`, `format --verify-no-changes`, coverage-threshold gate on `test`. Parse fixes: emit `status: parse_error` on TRX namespace mismatch; downgrade empty-`counts` to `status: warning`; make 500-char failure-message truncation configurable.

## 6. Brownfield (`rules/global/brownfield.md`) on C# repos

`git grep -l <symbol>` pollutes with `bin/obj`. Rule uses Python idioms (`just test <path>`); .NET analog is `dotnet test --filter FullyQualifiedName~<symbol>`. Add .NET sidebar: enumerate via `dotnet sln list` before greping, run tests by filter expression.

## 7. Orchestrator / validator friction

1. **`git-ops` utility agent is not in `library.yaml`** → `schemas/execution_plan.py::load_agent_roster` rejects any step naming it. My S10 initially failed validation; I retargeted to `implementer` and inlined git-ops behavior. Register utility agents or widen the validator.
2. **`soup plan validate <path>` referenced by `.claude/commands/tasks.md:22` is unimplemented** in `orchestrator/cli.py`. Also surfaced in `docs/reviews/cycle1-critic-dx.md:95`; still open. I validated inline with `ExecutionPlanValidator.from_library('library.yaml').validate(plan)`.
3. **Empty `files_allowed` for Bash-only steps is ambiguous.** `docs/PATTERNS.md §0c.5` says empty = read-only, but a commit step writes nothing in the repo while running `git commit`. Clarify for build/commit/verify-only steps.

## 8. Ergonomic wins (keep)

Record DTOs + `[ApiController]` give free 400s; `WebApplicationFactory<Program>` is first-class integration testing; `Npgsql.EntityFrameworkCore.PostgreSQL` is drop-in once the UTC switch is set; `cli_wrappers/dotnet.py::test_cmd` JSON output beats stdout-grep — keep the shape, fix §1.2.

## 9. Concrete suggested changes

1. **`cli_wrappers/dotnet.py`:** add `ef-script`, `ef-remove`, `format`, coverage-threshold; fix TRX namespace robustness.
2. **`templates/dotnet-webapi-postgres/YourApi.Tests/YourApi.Tests.csproj`:** add `FluentAssertions 6.12.x`, `coverlet.collector 6.0.x`.
3. **Restructure template to `src/` + `tests/`** per `rules/dotnet/testing.md §1`.
4. **`library.yaml`:** register `git-ops`, `researcher`, `docs-scraper`, `doc-writer` (currently orphaned at `.claude/agents/utility/`).
5. **`orchestrator/cli.py`:** add `soup plan validate <path>` — one-liner wrapping `ExecutionPlanValidator.from_library`.
6. **`rules/dotnet/coding-standards.md`:** add §5.7 (Npgsql UTC), §6.4 (`[ApiController]` auto-400), §12 (URL kebab-case).
7. **`rules/postgres/migrations.md §1.4`:** co-ownership of C# migration class vs raw `.sql`.
8. **`rules/dotnet/testing.md §7.3`:** `WebApplicationFactory<Program>` + `partial class Program` marker; InMemory vs Testcontainers trade-off.

Artifacts under `C:\Users\ethan\AIEngineering\soup\mock-apps\asset-tracker\`.
