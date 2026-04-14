namespace Streck.AssetTracker.Models;

/// <summary>
/// A tracked lab asset (microscope, pipette, freezer, etc.).
/// Persisted to the <c>assets</c> table.
/// </summary>
public class Asset
{
    /// <summary>Application-generated UUID v7 (time-ordered).</summary>
    public Guid Id { get; set; }

    /// <summary>Coarse asset category, e.g. <c>microscope</c>, <c>pipette</c>.</summary>
    public string AssetType { get; set; } = string.Empty;

    /// <summary>Manufacturer-assigned serial number (unique).</summary>
    public string Serial { get; set; } = string.Empty;

    /// <summary>Manufacturer name. Optional for legacy assets.</summary>
    public string? Manufacturer { get; set; }

    /// <summary>FK to <see cref="Models.Location"/>.</summary>
    public Guid LocationId { get; set; }

    /// <summary>FK to <see cref="Models.Owner"/>.</summary>
    public Guid OwnerId { get; set; }

    /// <summary>Timestamp of last calibration, UTC. Null for non-calibrated assets.</summary>
    public DateTime? CalibratedAt { get; set; }

    /// <summary>When the next calibration is due, UTC. Null when not applicable.</summary>
    public DateTime? CalibrationDue { get; set; }

    /// <summary>Row creation timestamp, UTC.</summary>
    public DateTime CreatedAt { get; set; }

    /// <summary>Last-updated timestamp, UTC.</summary>
    public DateTime UpdatedAt { get; set; }
}
