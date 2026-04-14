# TypeScript — coding standards

Target: TypeScript 5.4+, Node 20+ for server code. Applies to non-React TS (Node services, CLIs, libraries, SDK wrappers). React-specific rules live in `rules/react/`.

## 1. `tsconfig.json` — strict

Minimum baseline (extend from this):

```jsonc
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "strictFunctionTypes": true,
    "strictBindCallApply": true,
    "alwaysStrict": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "exactOptionalPropertyTypes": true,
    "forceConsistentCasingInFileNames": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "declaration": true,
    "sourceMap": true,
    "outDir": "dist"
  }
}
```

`tsc --noEmit` must be clean on every commit.

## 2. No `any`

1. `any` is forbidden in new code. ESLint rule `@typescript-eslint/no-explicit-any: error`.
2. When typing library outputs that truly are unknown, use `unknown` and narrow it.
3. `// @ts-ignore` / `// @ts-nocheck` are forbidden. Use `// @ts-expect-error <ticket-id>` sparingly with a reason, and it MUST turn into a compile error once fixed (that's the point of `expect-error`).
4. Use generics, not `any`, when a function is polymorphic.

## 3. Narrow at the boundary with `zod`

1. Every external input (HTTP body, CLI arg, file read, env var) is parsed by a `zod` schema at the boundary.
2. Derive types from schemas, not the other way:

```ts
import { z } from 'zod';

export const Invoice = z.object({
  id: z.string().uuid(),
  totalCents: z.number().int().nonnegative(),
  status: z.enum(['open', 'paid', 'partial']),
});
export type Invoice = z.infer<typeof Invoice>;
```

3. Env vars: one schema, parsed once at startup, exposed as a frozen object. No `process.env.FOO` reads scattered throughout the code.

## 4. Types vs. interfaces

1. Use `type` for unions, intersections, primitives, and function signatures.
2. Use `interface` for object shapes that might be extended across declarations (rare in app code; common for plugin APIs).
3. Don't flip between them in the same codebase — pick and stick.

## 4a. Branded types for IDs

1. Never let a `UserId` and an `OrderId` be the same type at the type level. Brand them so the compiler rejects accidental substitution.

```ts
export type UserId = string & { readonly __brand: 'UserId' };
export type OrderId = string & { readonly __brand: 'OrderId' };

export const UserId = (raw: string): UserId => raw as UserId;
export const OrderId = (raw: string): OrderId => raw as OrderId;
```

2. Every entity-key type gets its own brand. Functions accept branded types, never bare `string`.
3. Combine with zod via `.brand<'UserId'>()` for parse-at-boundary branding.

## 4b. Discriminated unions over boolean flags

1. Prefer a tagged union over optional fields + flags. If `loading`, `error`, and `data` are mutually exclusive, model them that way:

```ts
type FetchState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; error: Error }
  | { status: 'success'; data: T };
```

2. This makes invalid states unrepresentable (no `loading: true, error: Error` combo) and enables exhaustiveness checks.
3. Never ship state shapes with `isLoading: boolean; isError: boolean; data: T | null` — the 2^3 × T combinations are mostly illegal.

## 4c. Exhaustiveness checks with `never`

1. Every `switch` on a discriminated union's tag MUST have a `default` branch that assigns to `never`. This makes the compiler fail when a new variant is added and a case is missed.

```ts
function render(s: FetchState<User>): string {
  switch (s.status) {
    case 'idle':    return 'Idle';
    case 'loading': return 'Loading...';
    case 'error':   return `Error: ${s.error.message}`;
    case 'success': return `Hello, ${s.data.name}`;
    default: {
      const _exhaustive: never = s;
      throw new Error(`Unhandled state: ${JSON.stringify(_exhaustive)}`);
    }
  }
}
```

2. Same pattern works for `if/else` chains that narrow a union — bind the final `else` branch to `never`.

## 5. Null handling

1. Prefer `undefined` over `null` for "not yet set" / "optional." Use `null` only when interacting with a system that distinguishes them (JSON APIs, DBs).
2. Use optional chaining (`a?.b`) and nullish coalescing (`x ?? default`) — never `||` for defaults (coerces `0` / `""`).
3. Non-null assertion `!` is forbidden except immediately after a runtime check that the compiler can't see (comment required).

## 6. Async

1. Every async function returns `Promise<T>`. Never `Promise<any>`.
2. `await` every promise, or explicitly `void` it (`void fireAndForget()`).
3. Use `AbortSignal` for cancellation. Pipe through to `fetch`, `setTimeout` wrappers, etc.
4. Top-level: catch at the highest-level handler (HTTP error middleware, CLI main) and log+exit. Don't swallow.

## 7. Error handling

1. Define a tagged discriminated-union for domain errors, or a class hierarchy. Pick one.
2. Don't throw `string`s or object literals. Always `Error` or subclass.
3. Use `Result<T, E>` (`neverthrow` or hand-rolled) when error-as-value improves the API (parsers, validators); throw for truly exceptional paths.

## 8. Modules

1. ES modules only (`"type": "module"`). Extensions required in imports: `import { x } from './y.js'` (TS preserves).
2. Barrel files (`index.ts`) only at package boundaries — not for every internal folder (bundle/size cost).
3. **No default exports.** Always named exports. Default exports break tooling:
   - Renames don't propagate — IDE jumps to wrong symbol on rename.
   - Auto-import picks arbitrary local names, fragmenting the codebase (`import Foo` here, `import FooBar` there).
   - Tree-shakers handle named exports better.
   - Default exports can't be re-exported by name without a rebind.

   The ESLint rule `import/no-default-export: error` must be enabled.
   Exception (narrow): framework-mandated default exports (Next.js
   page files, some CLI entry points) — document each with a `// eslint-disable-next-line` comment citing the framework requirement.

## 8a. Return type annotations on exported functions

1. **Every exported function, method, and class member MUST declare a return type.** Inference is fine inside a module; at the boundary, an explicit annotation is the API contract.

```ts
// Good — return type is the contract
export function computeTotal(items: readonly Item[]): number {
  return items.reduce((sum, i) => sum + i.priceCents, 0);
}

// Bad — callers are at the mercy of implementation drift
export function computeTotal(items: readonly Item[]) {
  return items.reduce((sum, i) => sum + i.priceCents, 0);
}
```

2. Enforce via `@typescript-eslint/explicit-module-boundary-types: error`.
3. Async functions: the explicit type is `Promise<T>`, never bare `T` (the compiler will infer, but the annotation documents the asyncness).
4. Internal (non-exported) helpers may rely on inference. Inference is a feature for locals, a bug for public APIs.

## 9. Formatting & linting

1. `eslint` + `prettier` (or `biome`). Pick one formatter per repo.
2. Enable `@typescript-eslint/strict-type-checked` + `stylistic-type-checked`.
3. Enforce import order (external → internal → relative) via ESLint.
4. Line length 100; `prettier --check` on CI.

## 10. Testing

1. Vitest is preferred (Node) — same API as Jest, fewer gotchas. Fall back to Jest only in legacy.
2. Tests next to source: `foo.ts` + `foo.test.ts`.
3. One behavior per test. Fast: no network, no real filesystem (use `memfs` or `tmp`).
4. Coverage ≥80% via V8 provider (`--coverage`).

## 11. Dependencies

1. Pin `typescript` exactly — minor bumps change semantics.
2. `npm audit` / `pnpm audit` must be clean on CI; critical CVEs block merge.
3. Prefer `pnpm` for monorepos; `npm` for single-package projects. Mixing managers in one repo is forbidden.

## 12. Checklist

- [ ] `tsc --noEmit` clean
- [ ] `eslint` clean (with `strict-type-checked`)
- [ ] No `any`, no `!`, no `// @ts-ignore`
- [ ] All external inputs parsed via `zod`
- [ ] Tests green, coverage ≥80%
