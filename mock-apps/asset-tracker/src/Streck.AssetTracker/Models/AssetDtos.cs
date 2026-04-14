namespace Streck.AssetTracker.Models;

/// <summary>
/// Request body for <c>POST /api/v1/assets</c>.
/// </summary>
/// <param name="AssetType">Coarse category (e.g. <c>microscope</c>).</param>
/// <param name="Serial">Manufacturer serial number. Must be unique.</param>
/// <param name="Manufacturer">Optional manufacturer label.</param>
/// <param name="LocationId">FK to an existing <see cref="Location"/>.</param>
/// <param name="OwnerId">FK to an existing <see cref="Owner"/>.</param>
/// <param name="CalibratedAt">UTC timestamp of last calibration; optional.</param>
/// <param name="CalibrationDue">UTC timestamp when next calibration is due; optional.</param>
public sealed record CreateAssetRequest(
    string AssetType,
    string Serial,
    string? Manufacturer,
    Guid LocationId,
    Guid OwnerId,
    DateTime? CalibratedAt,
    DateTime? CalibrationDue);

/// <summary>
/// Request body for <c>PATCH /api/v1/assets/{id}</c>. All fields optional.
/// </summary>
public sealed record UpdateAssetRequest(
    string? AssetType,
    string? Serial,
    string? Manufacturer,
    Guid? LocationId,
    Guid? OwnerId,
    DateTime? CalibratedAt,
    DateTime? CalibrationDue);

/// <summary>
/// Response body for asset reads.
/// </summary>
public sealed record AssetResponse(
    Guid Id,
    string AssetType,
    string Serial,
    string? Manufacturer,
    Guid LocationId,
    Guid OwnerId,
    DateTime? CalibratedAt,
    DateTime? CalibrationDue,
    DateTime CreatedAt,
    DateTime UpdatedAt);

/// <summary>Response shape for <c>GET /health</c>.</summary>
public sealed record HealthResponse(string Status, bool Db);
