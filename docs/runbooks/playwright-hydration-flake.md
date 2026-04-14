# Playwright — test flakes on hydration race (Next.js / RSC)

## Symptom

Tests pass locally, flake on CI, or flake only under `--project=chromium`
after a cold browser start:

```
Error: expect(locator).toBeVisible() failed
  Expected: visible
  Received: hidden
```

```
Error: locator.click: Target page, context or browser has been closed
```

```
Error: element not attached to the DOM
```

Most commonly on pages where an interactive control lives inside a
`'use client'` island — shadcn `cmdk` popovers, Radix dropdowns,
`DataGrid` filters, faction chips, etc. The control renders server-side,
Playwright navigates to it, clicks before React hydrates, and the
click is swallowed.

Exact symptom observed in Middle-Earth-App dogfood (Scenario B):
`explorer.spec.ts` clicked a faction chip inside a `'use client'`
Command palette before React attached its listener.

## Cause

Next.js App Router streams HTML early — the visible DOM is present
*before* the client runtime has hydrated and attached event listeners.
A Playwright `click()` against a newly-loaded page can land in the
window where:

1. The element is in the DOM (Playwright's auto-wait is satisfied).
2. React has not yet attached the `onClick` handler.
3. The click event fires → no listener → nothing happens.

This is a genuine hydration race, not a Playwright bug.

## Fix

### Pattern 1: wait for network idle (simple, heavyweight)

Good enough for most tests. `networkidle` waits for at least 500 ms
without active network requests, which is a reasonable proxy for
"streaming done, hydrate complete":

```typescript
await page.goto('/characters');
await page.waitForLoadState('networkidle');
await page.getByRole('button', { name: 'Elf' }).click();
```

**Caveat:** this busts on pages that poll (`setInterval`-driven
updates, analytics beacons). If you see `networkidle` never
resolving, fall back to pattern 2 or 3.

### Pattern 2: wait for a specific response (surgical, lightweight)

When you know exactly which server request gates hydration:

```typescript
const charactersReq = page.waitForResponse(
  (r) => r.url().includes('/api/characters') && r.ok(),
);
await page.goto('/characters');
await charactersReq;
await page.getByRole('button', { name: 'Elf' }).click();
```

Prefer this when the hydration trigger is a well-known endpoint —
it is the fastest and least flaky option.

### Pattern 3: hydration sentinel (most robust)

Add a `data-hydrated="true"` attribute at the top of your root client
component once it mounts:

```tsx
'use client';
import { useEffect } from 'react';

export function HydrationSentinel() {
  useEffect(() => {
    document.documentElement.dataset.hydrated = 'true';
  }, []);
  return null;
}
```

Render it in `src/app/layout.tsx` once. In tests:

```typescript
await page.goto('/characters');
await page.locator('html[data-hydrated="true"]').waitFor();
await page.getByRole('button', { name: 'Elf' }).click();
```

This is the only pattern that deterministically survives every kind of
streaming / cache variation. Use it when flakes persist after patterns
1 and 2.

### Don't: arbitrary `waitForTimeout`

```typescript
// anti-pattern — ships latency to the happy path forever
await page.waitForTimeout(1000);
```

Fixed sleeps make green CI today and a slow / still-flaky suite
tomorrow. Use the signal-based waits above.

## Related

- `.claude/skills/systematic-debugging/SKILL.md` — if the fix doesn't
  hold, run the 4-phase process; do not stack more waits.
- `rules/react/coding-standards.md` — Playwright + `beforeEach` seed
  pattern.
- `rules/nextjs/app-router.md` (if present) — Server Component vs.
  `'use client'` boundaries.
- Middle-Earth-App dogfood: `docs/real-world-dogfood/middle-earth-app.md`
  Scenario B.
