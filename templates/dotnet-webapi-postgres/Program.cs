using Microsoft.EntityFrameworkCore;
using YourApi.Data;

var builder = WebApplication.CreateBuilder(args);

// Services
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var cs = builder.Configuration.GetConnectionString("Postgres")
         ?? throw new InvalidOperationException(
             "ConnectionStrings:Postgres is required — set it via appsettings.json, " +
             "user-secrets, or the ConnectionStrings__Postgres env var.");
builder.Services.AddDbContext<AppDbContext>(opt => opt.UseNpgsql(cs));

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.MapControllers();

// Minimal root endpoint
app.MapGet("/", () => Results.Ok(new { service = "your-api", version = "0.1.0" }));

app.Run();

/// <summary>Public entry point marker for WebApplicationFactory-based tests.</summary>
public partial class Program { }
