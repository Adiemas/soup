using System.Threading.Tasks;
using Testcontainers.PostgreSql;
using Xunit;

namespace YourApi.Tests;

/// <summary>
/// Shared Postgres container for the test run. Use via a collection fixture so
/// the container spins up once (it's the slow part) and tests inside the same
/// collection share connection strings.
/// </summary>
/// <remarks>
/// Per <c>rules/dotnet/testing.md §7</c>, integration tests run against
/// Testcontainers Postgres — never against EF Core InMemory, which mis-emulates
/// Npgsql semantics (case sensitivity, JSON ops, timestamptz, concurrency).
/// </remarks>
public sealed class PostgresFixture : IAsyncLifetime
{
    private readonly PostgreSqlContainer _container = new PostgreSqlBuilder()
        .WithImage("postgres:16-alpine")
        .WithDatabase("app_test")
        .WithUsername("test")
        .WithPassword("test")
        .Build();

    /// <summary>Npgsql connection string pointing at the running container.</summary>
    public string ConnectionString => _container.GetConnectionString();

    /// <inheritdoc />
    public async Task InitializeAsync()
    {
        await _container.StartAsync();
    }

    /// <inheritdoc />
    public async Task DisposeAsync()
    {
        await _container.DisposeAsync();
    }
}

/// <summary>xUnit collection binder so tests share a single <see cref="PostgresFixture"/>.</summary>
[CollectionDefinition("Postgres")]
public sealed class PostgresCollection : ICollectionFixture<PostgresFixture>
{
    // Marker only; xUnit wires the fixture through ICollectionFixture.
}
