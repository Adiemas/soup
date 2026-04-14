using Microsoft.EntityFrameworkCore;
using Streck.AssetTracker.Data;

// Npgsql 6+ is UTC-only for timestamptz; disable the legacy behaviour so
// DateTime.Kind = Utc is enforced and round-trips are deterministic.
AppContext.SetSwitch("Npgsql.EnableLegacyTimestampBehavior", false);

var builder = WebApplication.CreateBuilder(args);

// Services
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var connectionString = builder.Configuration.GetConnectionString("Postgres")
    ?? "Host=localhost;Port=5432;Database=assets;Username=app;Password=app";

builder.Services.AddDbContext<AppDbContext>(options => options.UseNpgsql(connectionString));

// Structured request logging (NFR-2).
builder.Services.AddLogging(logging => logging.AddSimpleConsole(o =>
{
    o.IncludeScopes = true;
    o.SingleLine = true;
}));

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();
app.MapControllers();

// Minimal root endpoint.
app.MapGet("/", () => Results.Ok(new { service = "streck-asset-tracker", version = "0.1.0" }));

app.Run();

/// <summary>Public entry point marker so <c>WebApplicationFactory&lt;Program&gt;</c> can bind.</summary>
public partial class Program { }
