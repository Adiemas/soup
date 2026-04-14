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

/// <summary>Integration tests for <c>api/v1/assets</c> CRUD.</summary>
public class AssetsControllerTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly WebApplicationFactory<Program> _factory;

    /// <summary>Wires the factory with a fresh, unique in-memory DbContext per test class instance.</summary>
    public AssetsControllerTests(WebApplicationFactory<Program> factory)
    {
        ArgumentNullException.ThrowIfNull(factory);
        var dbName = "assets-tests-" + Guid.NewGuid().ToString("N");
        _factory = factory.WithWebHostBuilder(b =>
        {
            b.ConfigureServices(services =>
            {
                var descriptor = services.Single(d => d.ServiceType == typeof(DbContextOptions<AppDbContext>));
                services.Remove(descriptor);
                services.AddDbContext<AppDbContext>(o => o.UseInMemoryDatabase(dbName));
            });
        });
    }

    [Fact]
    public async Task Post_ValidPayload_Returns201AndRoundTripsViaGet()
    {
        // Arrange
        var client = _factory.CreateClient();
        var (locationId, ownerId) = await SeedRefs();

        var request = new CreateAssetRequest(
            AssetType: "microscope",
            Serial: "SN-0001",
            Manufacturer: "Zeiss",
            LocationId: locationId,
            OwnerId: ownerId,
            CalibratedAt: DateTime.UtcNow.AddDays(-10),
            CalibrationDue: DateTime.UtcNow.AddDays(20));

        // Act
        var postResp = await client.PostAsJsonAsync("/api/v1/assets", request);

        // Assert
        postResp.StatusCode.Should().Be(HttpStatusCode.Created);
        var created = await postResp.Content.ReadFromJsonAsync<AssetResponse>();
        created.Should().NotBeNull();
        created!.Serial.Should().Be("SN-0001");

        var getResp = await client.GetAsync($"/api/v1/assets/{created.Id}");
        getResp.StatusCode.Should().Be(HttpStatusCode.OK);
        var fetched = await getResp.Content.ReadFromJsonAsync<AssetResponse>();
        fetched.Should().BeEquivalentTo(created, opt => opt.Excluding(x => x.UpdatedAt).Excluding(x => x.CreatedAt));
    }

    [Fact]
    public async Task Get_UnknownId_Returns404()
    {
        var client = _factory.CreateClient();
        var resp = await client.GetAsync($"/api/v1/assets/{Guid.NewGuid()}");
        resp.StatusCode.Should().Be(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task Patch_ChangesLocation_PreservesOtherFields()
    {
        var client = _factory.CreateClient();
        var (locationId, ownerId) = await SeedRefs();
        var created = await CreateMicroscope(client, locationId, ownerId);

        var newLocation = Guid.NewGuid();
        await SeedLocation(newLocation, "Bench 4", "OMA-A");

        var patch = new UpdateAssetRequest(
            AssetType: null, Serial: null, Manufacturer: null,
            LocationId: newLocation, OwnerId: null,
            CalibratedAt: null, CalibrationDue: null);

        var patchResp = await client.PatchAsJsonAsync($"/api/v1/assets/{created.Id}", patch);
        patchResp.StatusCode.Should().Be(HttpStatusCode.OK);
        var patched = await patchResp.Content.ReadFromJsonAsync<AssetResponse>();
        patched.Should().NotBeNull();
        patched!.LocationId.Should().Be(newLocation);
        patched.Serial.Should().Be(created.Serial);
        patched.OwnerId.Should().Be(created.OwnerId);
    }

    [Fact]
    public async Task Delete_RemovesAsset_AndIsIdempotentOnFirstCall()
    {
        var client = _factory.CreateClient();
        var (locationId, ownerId) = await SeedRefs();
        var created = await CreateMicroscope(client, locationId, ownerId);

        var firstDelete = await client.DeleteAsync($"/api/v1/assets/{created.Id}");
        firstDelete.StatusCode.Should().Be(HttpStatusCode.NoContent);

        var secondDelete = await client.DeleteAsync($"/api/v1/assets/{created.Id}");
        secondDelete.StatusCode.Should().Be(HttpStatusCode.NotFound);

        var getAfter = await client.GetAsync($"/api/v1/assets/{created.Id}");
        getAfter.StatusCode.Should().Be(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task List_CalibrationDueFilter_OnlyReturnsAssetsInWindow()
    {
        var client = _factory.CreateClient();
        var (locationId, ownerId) = await SeedRefs();

        var dueSoon = await client.PostAsJsonAsync("/api/v1/assets", new CreateAssetRequest(
            "pipette", "P-1", null, locationId, ownerId, null, DateTime.UtcNow.AddDays(5)));
        dueSoon.EnsureSuccessStatusCode();

        var dueLater = await client.PostAsJsonAsync("/api/v1/assets", new CreateAssetRequest(
            "pipette", "P-2", null, locationId, ownerId, null, DateTime.UtcNow.AddDays(60)));
        dueLater.EnsureSuccessStatusCode();

        var cutoff = DateTime.UtcNow.AddDays(30).ToString("O");
        var listResp = await client.GetAsync($"/api/v1/assets?calibrationDueBefore={Uri.EscapeDataString(cutoff)}");
        listResp.StatusCode.Should().Be(HttpStatusCode.OK);
        var assets = await listResp.Content.ReadFromJsonAsync<List<AssetResponse>>();
        assets.Should().NotBeNull();
        assets!.Select(a => a.Serial).Should().Contain("P-1").And.NotContain("P-2");
    }

    [Fact]
    public async Task Post_MissingSerial_Returns400()
    {
        var client = _factory.CreateClient();
        var (locationId, ownerId) = await SeedRefs();
        var response = await client.PostAsJsonAsync("/api/v1/assets", new CreateAssetRequest(
            "microscope", "", null, locationId, ownerId, null, null));
        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }

    // ------------------------------------------------------------------
    // helpers
    // ------------------------------------------------------------------

    private async Task<AssetResponse> CreateMicroscope(HttpClient client, Guid locationId, Guid ownerId)
    {
        var resp = await client.PostAsJsonAsync("/api/v1/assets", new CreateAssetRequest(
            "microscope", "SN-" + Guid.NewGuid().ToString("N")[..8], "Zeiss",
            locationId, ownerId,
            DateTime.UtcNow.AddDays(-1), DateTime.UtcNow.AddDays(30)));
        resp.EnsureSuccessStatusCode();
        var body = await resp.Content.ReadFromJsonAsync<AssetResponse>();
        body.Should().NotBeNull();
        return body!;
    }

    private async Task<(Guid locationId, Guid ownerId)> SeedRefs()
    {
        var locationId = Guid.NewGuid();
        var ownerId = Guid.NewGuid();
        await SeedLocation(locationId, "Bench 3", "OMA-A");
        await SeedOwner(ownerId, "Ada Streck", "ada@streck.example");
        return (locationId, ownerId);
    }

    private async Task SeedLocation(Guid id, string name, string site)
    {
        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        db.Locations.Add(new Location { Id = id, Name = name, Site = site, CreatedAt = DateTime.UtcNow });
        await db.SaveChangesAsync();
    }

    private async Task SeedOwner(Guid id, string name, string email)
    {
        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        db.Owners.Add(new Owner { Id = id, Name = name, Email = email, CreatedAt = DateTime.UtcNow });
        await db.SaveChangesAsync();
    }
}
