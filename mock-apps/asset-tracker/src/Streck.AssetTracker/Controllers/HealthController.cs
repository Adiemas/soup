using Microsoft.AspNetCore.Mvc;
using Streck.AssetTracker.Data;
using Streck.AssetTracker.Models;

namespace Streck.AssetTracker.Controllers;

/// <summary>Health / liveness probe endpoints.</summary>
[ApiController]
[Route("health")]
public sealed class HealthController : ControllerBase
{
    private readonly AppDbContext _db;
    private readonly ILogger<HealthController> _log;

    /// <summary>Constructs the controller with its dependencies.</summary>
    public HealthController(AppDbContext db, ILogger<HealthController> log)
    {
        ArgumentNullException.ThrowIfNull(db);
        ArgumentNullException.ThrowIfNull(log);
        _db = db;
        _log = log;
    }

    /// <summary>Returns the service status and a DB round-trip check.</summary>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>200 with <see cref="HealthResponse"/>.</returns>
    [HttpGet]
    public async Task<ActionResult<HealthResponse>> Get(CancellationToken ct = default)
    {
        bool dbOk;
        try
        {
            dbOk = await _db.Database.CanConnectAsync(ct).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            _log.LogWarning(ex, "health: DB round-trip failed");
            dbOk = false;
        }

        return Ok(new HealthResponse(dbOk ? "ok" : "degraded", dbOk));
    }
}
