using System.Net;
using System.Net.Http.Json;
using FluentAssertions;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Streck.AssetTracker.Data;
using Streck.AssetTracker.Models;
using Xunit;

namespace Streck.AssetTracker.Tests.Controllers;

/// <summary>Integration tests for <c>GET /health</c>.</summary>
public class HealthControllerTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly WebApplicationFactory<Program> _factory;

    /// <summary>Wires the factory with an in-memory DbContext override.</summary>
    public HealthControllerTests(WebApplicationFactory<Program> factory)
    {
        ArgumentNullException.ThrowIfNull(factory);
        _factory = factory.WithWebHostBuilder(b =>
        {
            b.ConfigureServices(services =>
            {
                var descriptor = services.Single(d => d.ServiceType == typeof(DbContextOptions<AppDbContext>));
                services.Remove(descriptor);
                services.AddDbContext<AppDbContext>(o => o.UseInMemoryDatabase("health-tests"));
            });
        });
    }

    [Fact]
    public async Task Get_WithReachableDb_ReturnsOkAndStatusOk()
    {
        // Arrange
        var client = _factory.CreateClient();

        // Act
        var response = await client.GetAsync("/health");

        // Assert
        response.StatusCode.Should().Be(HttpStatusCode.OK);
        var body = await response.Content.ReadFromJsonAsync<HealthResponse>();
        body.Should().NotBeNull();
        body!.Status.Should().Be("ok");
        body.Db.Should().BeTrue();
    }

    [Fact]
    public async Task Root_ReturnsServiceMetadata()
    {
        var client = _factory.CreateClient();
        var response = await client.GetAsync("/");
        response.StatusCode.Should().Be(HttpStatusCode.OK);
    }
}
