namespace YourApi.Models;

/// <summary>
/// Response shape for <c>GET /health</c>.
/// </summary>
/// <param name="Status">Overall status; "ok" or "degraded".</param>
/// <param name="Db">True when a Postgres round-trip succeeded.</param>
public record HealthResponse(string Status, bool Db);
