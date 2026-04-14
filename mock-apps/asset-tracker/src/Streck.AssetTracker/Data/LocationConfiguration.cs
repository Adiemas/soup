using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Streck.AssetTracker.Models;

namespace Streck.AssetTracker.Data;

/// <summary>EF Core configuration for <see cref="Location"/>.</summary>
internal sealed class LocationConfiguration : IEntityTypeConfiguration<Location>
{
    /// <inheritdoc />
    public void Configure(EntityTypeBuilder<Location> builder)
    {
        ArgumentNullException.ThrowIfNull(builder);
        builder.ToTable("locations");
        builder.HasKey(l => l.Id);
        builder.Property(l => l.Id).HasColumnName("id").HasDefaultValueSql("gen_random_uuid()");
        builder.Property(l => l.Name).HasColumnName("name").IsRequired();
        builder.Property(l => l.Site).HasColumnName("site").IsRequired();
        builder.Property(l => l.CreatedAt).HasColumnName("created_at").HasDefaultValueSql("now()");
    }
}
