# your-app — React + TypeScript + Vite

Scaffolded from the soup `react-ts-vite` template.

## Quick start

```bash
just init
just dev       # http://localhost:5173
```

The dev server proxies `/api/*` to `http://localhost:8000` by default.
Override with `VITE_API_TARGET=http://other-host:port just dev`.

## Tests

```bash
just test
```

## Build

```bash
just build     # static bundle in dist/
docker build -t your-app:latest .
```

## Layout

See `CLAUDE.md` for the agent contract.
