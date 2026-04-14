using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using YourApi.Data;
using YourApi.Models;

namespace YourApi.Controllers;

/// <summary>Health/liveness endpoints.</summary>
[ApiController]
[Route("health")]
public class HealthController : ControllerBase
{
    private readonly AppDbContext _db;

    /// <summary>Creates the controller.</summary>
    public HealthController(AppDbContext db) => _db = db;

    /// <summary>Returns service health, including a DB round-trip check.</summary>
    [HttpGet]
    public async Task<ActionResult<HealthResponse>> Get()
    {
        bool dbOk;
        try
        {
            dbOk = await _db.Database.CanConnectAsync();
        }
        catch
        {
            dbOk = false;
        }
        return Ok(new HealthResponse(dbOk ? "ok" : "degraded", dbOk));
    }
}
