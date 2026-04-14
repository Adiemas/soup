# Project rules (ts-node-script)

Scaffolded from the soup `ts-node-script` template. Parent `CLAUDE.md` +
`CONSTITUTION.md` iron laws apply.

## Stack

- **Runtime:** Node 22+ (ESM only)
- **Launcher:** `tsx` in dev, plain `node` on `dist/` in prod
- **Language:** TypeScript strict (`noUncheckedIndexedAccess`, `noImplicitReturns`)
- **Boundary validation:** `zod` on every argv/stdin/network/file read
- **Tests:** Vitest (colocated `*.test.ts`)
- **Secret scanning:** gitleaks with a committed `.gitleaks.toml`

## Layout

```
src/
  main.ts         entry; argv parsing; dispatch
  adapter.ts      one adapter per external source
  adapter.test.ts vitest suite colocated
.gitleaks.toml    custom rules for Anthropic/Slack/AWS
.github/
  workflows/
    ci.yml        typecheck + test + gitleaks scan
tsconfig.json     strict
justfile          dev/test/run/build/lint/typecheck/scan
```

## Rules for agents

1. **No frontend and no HTTP server here.** If the project needs one,
   scaffold a sibling from a different template — do not mix concerns.
2. **Validate at the boundary.** `zod` on argv (see `main.ts`), stdin,
   network responses, and file reads. Reject unknown fields; cap sizes.
3. **Strict TypeScript.** No `any`, no `@ts-ignore`, no
   `@ts-expect-error` without a linked issue. Prefer `unknown` +
   narrowing. `noUncheckedIndexedAccess` is on — handle `undefined` from
   `array[i]` and `map.get(key)` explicitly.
4. **ESM only.** `"type": "module"` in `package.json`. Use
   `import ... from "./x.js"` (with the `.js` extension) — TS resolves
   via `moduleResolution: "bundler"`. Do not require CommonJS.
5. **One adapter per source kind.** Keep the `Adapter` contract tiny
   and stable (`fetch(input) -> Promise<Result>`). Test the adapter in
   isolation; do not test through `main`.
6. **Stub mode for expensive deps.** If the script calls an LLM / paid
   API, add an env-var knob (`ENRICHMENT_MODE=stub|live`) that short-
   circuits the call with deterministic fake output. CI runs in stub by
   default.
7. **Atomic writes for any file state.** Write to a tmp file in the
   same directory, then rename. See `rules/state-persistence/json-file.md`.
8. **Serialise concurrent runs at the orchestrator boundary.** GitHub
   Actions: `concurrency: <group-name>`. Cron on a VM: a lockfile in
   the state dir. Do not try to serialise inside the process.
9. **Secrets never in the repo.** `.gitleaks.toml` is committed; `.env`
   is gitignored; `.env.example` is the contract. CI runs gitleaks on
   every PR; a leaked secret must be rotated before the merge.
10. **Lockfile is authoritative in CI.** `npm ci` / `pnpm install
    --frozen-lockfile` / `yarn install --frozen-lockfile` — never
    plain `install` in CI.

## Local dev

```bash
just init
just run help              # argv parser demo
just run run --source x    # real run
just test
just typecheck
just scan                  # gitleaks
```
