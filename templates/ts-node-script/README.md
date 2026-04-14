# your-script -- TypeScript Node script

Scaffolded from the soup `ts-node-script` template. Pure TS; no frontend,
no HTTP server, no DB.

## Quick start

```bash
just init
just run help           # prints usage
just run dry-run --source local --limit 5
```

## Tests

```bash
just test
```

## Build + deploy

```bash
just build              # emits dist/
just start              # node dist/main.js
```

## Secret scan

```bash
just scan               # gitleaks detect --config .gitleaks.toml
```

CI runs `typecheck + test + gitleaks` on every PR.

## Layout

See `CLAUDE.md` for the agent contract.
