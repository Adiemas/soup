using Microsoft.EntityFrameworkCore;
using Streck.AssetTracker.Models;

namespace Streck.AssetTracker.Data;

/// <summary>
/// EF Core <see cref="DbContext"/> for the Asset Tracker service.
/// Scoped per-request (<c>AddDbContext&lt;AppDbContext&gt;</c>) per
/// <c>rules/dotnet/coding-standards.md §4</c>.
/// </summary>
public class AppDbContext : DbContext
{
    /// <summary>Creates a new <see cref="AppDbContext"/>.</summary>
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    /// <summary>All tracked assets.</summary>
    public DbSet<Asset> Assets => Set<Asset>();

    /// <summary>All locations.</summary>
    public DbSet<Location> Locations => Set<Location>();

    /// <summary>All owners.</summary>
    public DbSet<Owner> Owners => Set<Owner>();

    /// <summary>Wire <see cref="IEntityTypeConfiguration{TEntity}"/> classes from this assembly.</summary>
    /// <param name="modelBuilder">EF Core model builder.</param>
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        ArgumentNullException.ThrowIfNull(modelBuilder);
        modelBuilder.ApplyConfigurationsFromAssembly(typeof(AppDbContext).Assembly);
        base.OnModelCreating(modelBuilder);
    }
}
