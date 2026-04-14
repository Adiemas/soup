using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Streck.AssetTracker.Data;
using Streck.AssetTracker.Models;

namespace Streck.AssetTracker.Controllers;

/// <summary>CRUD + filter endpoints for <see cref="Asset"/>.</summary>
[ApiController]
[Route("api/v1/assets")]
public sealed class AssetsController : ControllerBase
{
    private readonly AppDbContext _db;
    private readonly ILogger<AssetsController> _log;

    /// <summary>Constructs the controller.</summary>
    public AssetsController(AppDbContext db, ILogger<AssetsController> log)
    {
        ArgumentNullException.ThrowIfNull(db);
        ArgumentNullException.ThrowIfNull(log);
        _db = db;
        _log = log;
    }

    /// <summary>Lists assets, optionally filtered by location, owner, or calibration-due window.</summary>
    /// <param name="locationId">Restrict to this location.</param>
    /// <param name="ownerId">Restrict to this owner.</param>
    /// <param name="calibrationDueBefore">Only return assets whose <c>calibration_due</c> is on or before this timestamp.</param>
    /// <param name="ct">Cancellation token.</param>
    [HttpGet]
    public async Task<ActionResult<IReadOnlyList<AssetResponse>>> List(
        [FromQuery] Guid? locationId,
        [FromQuery] Guid? ownerId,
        [FromQuery] DateTime? calibrationDueBefore,
        CancellationToken ct = default)
    {
        IQueryable<Asset> q = _db.Assets.AsNoTracking();

        if (locationId.HasValue) q = q.Where(a => a.LocationId == locationId.Value);
        if (ownerId.HasValue) q = q.Where(a => a.OwnerId == ownerId.Value);
        if (calibrationDueBefore.HasValue)
        {
            var cutoff = DateTime.SpecifyKind(calibrationDueBefore.Value, DateTimeKind.Utc);
            q = q.Where(a => a.CalibrationDue != null && a.CalibrationDue <= cutoff);
        }

        var rows = await q.OrderBy(a => a.CreatedAt).Take(50).ToListAsync(ct).ConfigureAwait(false);
        return Ok(rows.Select(ToResponse).ToList());
    }

    /// <summary>Gets a single asset by id.</summary>
    [HttpGet("{id:guid}")]
    public async Task<ActionResult<AssetResponse>> GetById(Guid id, CancellationToken ct = default)
    {
        var entity = await _db.Assets.AsNoTracking().FirstOrDefaultAsync(a => a.Id == id, ct).ConfigureAwait(false);
        return entity is null ? NotFound() : Ok(ToResponse(entity));
    }

    /// <summary>Creates a new asset.</summary>
    [HttpPost]
    public async Task<ActionResult<AssetResponse>> Create(
        [FromBody] CreateAssetRequest request,
        CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(request);

        if (string.IsNullOrWhiteSpace(request.AssetType)) return BadRequest("asset_type is required");
        if (string.IsNullOrWhiteSpace(request.Serial)) return BadRequest("serial is required");

        var entity = new Asset
        {
            Id = NewUuidV7(),
            AssetType = request.AssetType,
            Serial = request.Serial,
            Manufacturer = request.Manufacturer,
            LocationId = request.LocationId,
            OwnerId = request.OwnerId,
            CalibratedAt = Utc(request.CalibratedAt),
            CalibrationDue = Utc(request.CalibrationDue),
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
        };

        try
        {
            _db.Assets.Add(entity);
            await _db.SaveChangesAsync(ct).ConfigureAwait(false);
        }
        catch (DbUpdateException ex)
        {
            // REQ-9: FK violation or unique-serial collision -> 422.
            _log.LogWarning(ex, "create asset failed due to DB constraint");
            return UnprocessableEntity(new { error = "constraint violation", detail = ex.InnerException?.Message ?? ex.Message });
        }

        var response = ToResponse(entity);
        return CreatedAtAction(nameof(GetById), new { id = entity.Id }, response);
    }

    /// <summary>Partially updates an asset.</summary>
    [HttpPatch("{id:guid}")]
    public async Task<ActionResult<AssetResponse>> Patch(
        Guid id,
        [FromBody] UpdateAssetRequest request,
        CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(request);

        var entity = await _db.Assets.FirstOrDefaultAsync(a => a.Id == id, ct).ConfigureAwait(false);
        if (entity is null) return NotFound();

        if (request.AssetType is not null) entity.AssetType = request.AssetType;
        if (request.Serial is not null) entity.Serial = request.Serial;
        if (request.Manufacturer is not null) entity.Manufacturer = request.Manufacturer;
        if (request.LocationId.HasValue) entity.LocationId = request.LocationId.Value;
        if (request.OwnerId.HasValue) entity.OwnerId = request.OwnerId.Value;
        if (request.CalibratedAt.HasValue) entity.CalibratedAt = Utc(request.CalibratedAt);
        if (request.CalibrationDue.HasValue) entity.CalibrationDue = Utc(request.CalibrationDue);
        entity.UpdatedAt = DateTime.UtcNow;

        await _db.SaveChangesAsync(ct).ConfigureAwait(false);
        return Ok(ToResponse(entity));
    }

    /// <summary>Deletes an asset. Returns 204 on first delete, 404 thereafter (hard delete).</summary>
    [HttpDelete("{id:guid}")]
    public async Task<IActionResult> Delete(Guid id, CancellationToken ct = default)
    {
        var entity = await _db.Assets.FirstOrDefaultAsync(a => a.Id == id, ct).ConfigureAwait(false);
        if (entity is null) return NotFound();

        _db.Assets.Remove(entity);
        await _db.SaveChangesAsync(ct).ConfigureAwait(false);
        return NoContent();
    }

    // ------------------------------------------------------------------
    // Internals
    // ------------------------------------------------------------------

    private static AssetResponse ToResponse(Asset a) => new(
        a.Id, a.AssetType, a.Serial, a.Manufacturer, a.LocationId, a.OwnerId,
        a.CalibratedAt, a.CalibrationDue, a.CreatedAt, a.UpdatedAt);

    private static DateTime? Utc(DateTime? value) =>
        value.HasValue ? DateTime.SpecifyKind(value.Value, DateTimeKind.Utc) : null;

    /// <summary>
    /// Minimal UUID v7 generator (time-ordered). Not cryptographically strong; good
    /// enough for B-tree insert locality per <c>rules/postgres/migrations.md §7.3</c>.
    /// </summary>
    private static Guid NewUuidV7()
    {
        Span<byte> bytes = stackalloc byte[16];
        Random.Shared.NextBytes(bytes);
        var unixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        bytes[0] = (byte)((unixMs >> 40) & 0xFF);
        bytes[1] = (byte)((unixMs >> 32) & 0xFF);
        bytes[2] = (byte)((unixMs >> 24) & 0xFF);
        bytes[3] = (byte)((unixMs >> 16) & 0xFF);
        bytes[4] = (byte)((unixMs >> 8) & 0xFF);
        bytes[5] = (byte)(unixMs & 0xFF);
        // Version (7) in high nibble of byte 6.
        bytes[6] = (byte)((bytes[6] & 0x0F) | 0x70);
        // Variant (10xxxxxx) in high bits of byte 8.
        bytes[8] = (byte)((bytes[8] & 0x3F) | 0x80);
        return new Guid(bytes);
    }
}
