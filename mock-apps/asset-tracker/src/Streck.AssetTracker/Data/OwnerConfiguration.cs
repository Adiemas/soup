using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Streck.AssetTracker.Models;

namespace Streck.AssetTracker.Data;

/// <summary>EF Core configuration for <see cref="Owner"/>.</summary>
internal sealed class OwnerConfiguration : IEntityTypeConfiguration<Owner>
{
    /// <inheritdoc />
    public void Configure(EntityTypeBuilder<Owner> builder)
    {
        ArgumentNullException.ThrowIfNull(builder);
        builder.ToTable("owners");
        builder.HasKey(o => o.Id);
        builder.Property(o => o.Id).HasColumnName("id").HasDefaultValueSql("gen_random_uuid()");
        builder.Property(o => o.Name).HasColumnName("name").IsRequired();
        builder.Property(o => o.Email).HasColumnName("email").IsRequired();
        builder.Property(o => o.CreatedAt).HasColumnName("created_at").HasDefaultValueSql("now()");

        builder.HasIndex(o => o.Email).IsUnique().HasDatabaseName("ux_owners_email");
    }
}
