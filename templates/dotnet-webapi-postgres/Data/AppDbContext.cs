using Microsoft.EntityFrameworkCore;

namespace YourApi.Data;

/// <summary>EF Core DbContext for the app.</summary>
public class AppDbContext : DbContext
{
    /// <summary>Creates a new <see cref="AppDbContext"/>.</summary>
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options)
    {
    }

    /// <summary>Schema version/metadata table.</summary>
    public DbSet<AppMeta> AppMeta => Set<AppMeta>();

    /// <summary>Health ping journal — a tiny seed entity the initial migration creates.</summary>
    public DbSet<Health> Health => Set<Health>();

    /// <inheritdoc />
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.Entity<AppMeta>(e =>
        {
            e.ToTable("app_meta");
            e.HasKey(m => m.Key);
            e.Property(m => m.Key).HasColumnName("key").HasMaxLength(128);
            e.Property(m => m.Value).HasColumnName("value");
        });

        modelBuilder.Entity<Health>(e =>
        {
            e.ToTable("health");
            e.HasKey(h => h.Id);
            e.Property(h => h.Id).HasColumnName("id");
            e.Property(h => h.Status).HasColumnName("status").HasMaxLength(32).IsRequired();
            e.Property(h => h.CheckedAt).HasColumnName("checked_at").HasColumnType("timestamptz");
        });
    }
}

/// <summary>Row in the <c>app_meta</c> table.</summary>
public class AppMeta
{
    /// <summary>Key (primary).</summary>
    public string Key { get; set; } = string.Empty;

    /// <summary>Value associated with the key.</summary>
    public string Value { get; set; } = string.Empty;
}

/// <summary>A single health-check journal entry in the <c>health</c> table.</summary>
public class Health
{
    /// <summary>Surrogate key.</summary>
    public Guid Id { get; set; }

    /// <summary>Short status string (<c>ok</c>, <c>degraded</c>, …).</summary>
    public string Status { get; set; } = "ok";

    /// <summary>UTC timestamp the check was recorded.</summary>
    public DateTime CheckedAt { get; set; } = DateTime.UtcNow;
}
