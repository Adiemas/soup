#if USE_INMEMORY
// -----------------------------------------------------------------------------
// InMemory variant — cheap, fast, but known to mis-emulate Npgsql semantics.
// Enable with `dotnet test -p:DefineConstants=USE_INMEMORY` when Docker is
// unavailable. Default (no define) uses the Testcontainers path below.
// -----------------------------------------------------------------------------
using System.Net;
using System.Net.Http.Json;
using FluentAssertions;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using YourApi.Data;
using YourApi.Models;
using Xunit;

namespace YourApi.Tests;

public sealed class HealthControllerTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly WebApplicationFactory<Program> _factory;

    public HealthControllerTests(WebApplicationFactory<Program> factory)
    {
        _factory = factory.WithWebHostBuilder(b =>
        {
            b.ConfigureServices(services =>
            {
                var descriptor = services.Single(d => d.ServiceType == typeof(DbContextOptions<AppDbContext>));
                services.Remove(descriptor);
                services.AddDbContext<AppDbContext>(o => o.UseInMemoryDatabase("tests"));
            });
        });
    }

    [Fact]
    public async Task Health_ReturnsOk()
    {
        var client = _factory.CreateClient();
        var resp = await client.GetAsync("/health");
        resp.StatusCode.Should().Be(HttpStatusCode.OK);
        var body = await resp.Content.ReadFromJsonAsync<HealthResponse>();
        body.Should().NotBeNull();
        body!.Status.Should().Be("ok");
    }
}
#else
// -----------------------------------------------------------------------------
// DEFAULT: Testcontainers-backed Postgres. Matches rules/dotnet/testing.md §7.
// Requires Docker on the host (CI: docker-in-docker or rootless).
// -----------------------------------------------------------------------------
using System.Net;
using System.Net.Http.Json;
using FluentAssertions;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using YourApi.Data;
using YourApi.Models;
using Xunit;

namespace YourApi.Tests;

/// <summary>
/// Integration tests for the <c>/health</c> endpoint backed by a real Postgres
/// container. Each test shares the container (collection fixture) but gets a
/// freshly migrated schema via <see cref="AppDbContext.Database.EnsureCreated"/>.
/// </summary>
[Collection("Postgres")]
public sealed class HealthControllerTests : IClassFixture<PostgresWebAppFactory>
{
    private readonly PostgresWebAppFactory _factory;

    public HealthControllerTests(PostgresWebAppFactory factory, PostgresFixture fixture)
    {
        factory.ConnectionString = fixture.ConnectionString;
        _factory = factory;
    }

    [Fact]
    public async Task Health_ReturnsOk()
    {
        var client = _factory.CreateClient();
        var resp = await client.GetAsync("/health");
        resp.StatusCode.Should().Be(HttpStatusCode.OK);
        var body = await resp.Content.ReadFromJsonAsync<HealthResponse>();
        body.Should().NotBeNull();
        body!.Status.Should().Be("ok");
        body.Db.Should().BeTrue();
    }

    [Fact]
    public async Task Root_ReturnsServiceMetadata()
    {
        var client = _factory.CreateClient();
        var resp = await client.GetAsync("/");
        resp.StatusCode.Should().Be(HttpStatusCode.OK);
    }
}

/// <summary>
/// <see cref="WebApplicationFactory{TEntryPoint}"/> that swaps the registered
/// <see cref="AppDbContext"/> connection string for the Testcontainers one and
/// runs <c>EnsureCreated</c> at startup so integration tests see a real schema.
/// </summary>
public sealed class PostgresWebAppFactory : WebApplicationFactory<Program>
{
    /// <summary>Container-backed connection string, injected by the fixture.</summary>
    public string ConnectionString { get; set; } = string.Empty;

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureAppConfiguration((_, config) =>
        {
            config.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ConnectionStrings:Postgres"] = ConnectionString,
            });
        });
        builder.ConfigureServices(services =>
        {
            var descriptor = services.Single(
                d => d.ServiceType == typeof(DbContextOptions<AppDbContext>));
            services.Remove(descriptor);
            services.AddDbContext<AppDbContext>(o => o.UseNpgsql(ConnectionString));

            // Ensure schema exists for integration tests.
            using var scope = services.BuildServiceProvider().CreateScope();
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            db.Database.EnsureCreated();
        });
    }
}
#endif
