# syntax=docker/dockerfile:1.7
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY src/Streck.AssetTracker/Streck.AssetTracker.csproj src/Streck.AssetTracker/
RUN dotnet restore src/Streck.AssetTracker/Streck.AssetTracker.csproj
COPY . .
RUN dotnet publish src/Streck.AssetTracker/Streck.AssetTracker.csproj \
    -c Release -o /app/publish --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=build /app/publish .
ENV ASPNETCORE_URLS=http://+:8080
ENV ASPNETCORE_ENVIRONMENT=Production
EXPOSE 8080
ENTRYPOINT ["dotnet", "Streck.AssetTracker.dll"]
