# syntax=docker/dockerfile:1.7
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY YourApi.csproj ./
RUN dotnet restore YourApi.csproj
COPY . .
RUN dotnet publish YourApi.csproj -c Release -o /app/publish --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=build /app/publish .
ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080
ENTRYPOINT ["dotnet", "YourApi.dll"]
