using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Streck.AssetTracker.Models;

namespace Streck.AssetTracker.Data;

/// <summary>EF Core configuration for <see cref="Asset"/>.</summary>
internal sealed class AssetConfiguration : IEntityTypeConfiguration<Asset>
{
    /// <inheritdoc />
    public void Configure(EntityTypeBuilder<Asset> builder)
    {
        ArgumentNullException.ThrowIfNull(builder);
        builder.ToTable("assets");
        builder.HasKey(a => a.Id);

        builder.Property(a => a.Id).HasColumnName("id");
        builder.Property(a => a.AssetType).HasColumnName("asset_type").IsRequired();
        builder.Property(a => a.Serial).HasColumnName("serial").IsRequired();
        builder.Property(a => a.Manufacturer).HasColumnName("manufacturer");
        builder.Property(a => a.LocationId).HasColumnName("location_id");
        builder.Property(a => a.OwnerId).HasColumnName("owner_id");
        builder.Property(a => a.CalibratedAt).HasColumnName("calibrated_at");
        builder.Property(a => a.CalibrationDue).HasColumnName("calibration_due");
        builder.Property(a => a.CreatedAt).HasColumnName("created_at").HasDefaultValueSql("now()");
        builder.Property(a => a.UpdatedAt).HasColumnName("updated_at").HasDefaultValueSql("now()");

        builder.HasIndex(a => a.Serial).IsUnique().HasDatabaseName("ux_assets_serial");
        builder.HasIndex(a => a.LocationId).HasDatabaseName("idx_assets_location_id");
        builder.HasIndex(a => a.OwnerId).HasDatabaseName("idx_assets_owner_id");
        builder.HasIndex(a => a.CalibrationDue).HasDatabaseName("idx_assets_calibration_due");

        builder.HasOne<Location>().WithMany().HasForeignKey(a => a.LocationId).OnDelete(DeleteBehavior.Restrict);
        builder.HasOne<Owner>().WithMany().HasForeignKey(a => a.OwnerId).OnDelete(DeleteBehavior.Restrict);
    }
}
