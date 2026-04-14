# Project rules (react-ts-vite)

Scaffolded from the soup `react-ts-vite` template. Parent `CLAUDE.md` +
`CONSTITUTION.md` iron laws apply.

## Stack

- **Build:** Vite 5
- **Framework:** React 18 (function components only)
- **Language:** TypeScript strict
- **Tests:** Vitest + React Testing Library + jsdom
- **Prod serve:** nginx (static dist/)

## Layout

```
src/
  main.tsx                 entry
  App.tsx                  root component
  components/
    Health.tsx             example consumer of /api/health
  __tests__/
    setup.ts               jest-dom matchers
    App.test.tsx           component tests
index.html
vite.config.ts             includes /api dev proxy
nginx.conf                 prod /api -> api:8000
```

## Rules for agents

1. **Function components + hooks only.** No class components.
2. **Strict TypeScript.** No `any`. No `@ts-ignore`. Prefer `unknown` + narrowing.
3. **Every component gets a test.** RTL + Vitest. Query by role/label/testid — not CSS classes.
4. **Network calls via `fetch`** to `/api/*`. Vite dev proxies to backend; nginx does so in prod.
5. **No inline styles** beyond tiny local tweaks; CSS/MUI/tokens when the project adopts them.
6. **Accessibility:** every interactive element has a role/label; images have `alt`.
7. **No `npm start`** — use `just dev`.
8. **Observability:** see `rules/observability/README.md` for
   structured logging (pino), correlation ids on fetch calls, and
   the `/health` + `/ready` + `/version` contract expected from the
   backend this SPA talks to.

## Local dev

```bash
just init
just dev       # vite dev server on :5173 (proxies /api to :8000)
just test
just build     # emits dist/
```
