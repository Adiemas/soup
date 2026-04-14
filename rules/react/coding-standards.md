# React — coding standards

Target: React 18+, TypeScript strict, Vite build, React Testing Library, Playwright for E2E.

## 1. Components

1. **Functional components only.** No class components, no `this`.
2. Name components in PascalCase; file name matches the default export.
3. One component per file when it's nontrivial. Multiple tiny helpers in one file are fine if co-located.
4. Props are typed via an explicit `type` or `interface`. Never `any`, never untyped.

```tsx
type InvoiceRowProps = {
  invoice: Invoice;
  onPay?: (id: string) => void;
};

export function InvoiceRow({ invoice, onPay }: InvoiceRowProps) {
  return (
    <tr>
      <td>{invoice.number}</td>
      <td>{formatCents(invoice.totalCents)}</td>
      <td>{onPay && <button onClick={() => onPay(invoice.id)}>Pay</button>}</td>
    </tr>
  );
}
```

## 2. Hooks — the rules of hooks

1. Hooks only at the top level. Never inside loops, conditions, or nested functions.
2. Only call hooks from React function components or custom hooks.
3. Custom hook names start with `use`: `useInvoice`, `useAuth`.
4. The exhaustive-deps ESLint rule is ON. Never silence with a blanket `// eslint-disable` — refactor to make the dependency explicit.

## 3. State & data

1. Server state → a fetch library (TanStack Query, SWR, or RTK Query). Don't hand-roll `useEffect + fetch` for data.
2. Client state (form, UI toggles) → `useState` / `useReducer`. No Redux for trivial state.
3. Global state (user, theme) → Context, behind a custom hook (`useAuth()`). Never consume Context directly in 10 places.
4. Never put server data in `useState` — cache invalidation is a bug factory.

## 4. Effects

1. `useEffect` is for synchronizing with external systems (subscriptions, DOM, timers). It is NOT for data fetching in well-served apps.
2. Every effect has a cleanup if it creates anything cancellable.

```tsx
useEffect(() => {
  const sub = bus.subscribe('invoice-paid', handler);
  return () => sub.unsubscribe();
}, [bus]);
```

3. Avoid `useLayoutEffect` unless you need to measure DOM pre-paint.

## 5. Performance

1. Don't pre-optimize. Measure with the React DevTools profiler first.
2. `React.memo`, `useMemo`, `useCallback` only when a profile shows a win. Default is plain.
3. Stable keys on lists. Never use array index as a key when items can be reordered.
4. Split bundles with `React.lazy` + `Suspense` for heavy routes.

## 6. Forms

1. Controlled components unless you specifically need uncontrolled (file inputs).
2. Use `react-hook-form` + `zod` for validation. Validate at the boundary.
3. Disable the submit button during in-flight submission; show the error in the same form, not in a toast.

## 7. Styling

1. Pick one system per app (Tailwind OR CSS modules OR Styled Components). Don't mix.
2. With Tailwind: colocate classes on the element; extract only when a pattern repeats ≥3 times.
3. Design tokens live in `tailwind.config.ts` or a theme file — never hard-code hexes in components.

## 8. Accessibility

1. Semantic HTML first (`<button>`, `<nav>`, `<ul>`) before ARIA hacks.
2. Every interactive element has a visible focus style.
3. Labels are associated with inputs (`<label htmlFor>` or wrapping).
4. Images have `alt`; decorative ones use `alt=""`.
5. Run `eslint-plugin-jsx-a11y` in CI.

## 9. Testing (React Testing Library)

1. Test behavior, not implementation. Query by role or text, not by class name:

```tsx
test('shows the total formatted in dollars', () => {
  render(<InvoiceRow invoice={inv({ totalCents: 12_345 })} />);
  expect(screen.getByRole('row')).toHaveTextContent('$123.45');
});
```

2. `userEvent` over `fireEvent` for interactions.
3. No snapshot tests for large trees. Snapshots are fine for small presentational components when the diff is meaningful.
4. For async: `await screen.findByRole(...)` or `await waitFor(...)`. Never `setTimeout`.
5. E2E: Playwright with one `beforeEach` that seeds an isolated dataset. No reliance on staging data.

## 10. Vite + TS

1. `tsconfig.json` extends the strict base and sets `noUncheckedIndexedAccess: true`.
2. `vite.config.ts` sets `resolve.alias` for `@/` → `src/`. Use `@/` in all intra-app imports.
3. Env vars via `import.meta.env.VITE_*`. Never read `process.env` in app code.

## 11. File layout

```
src/
  components/      # shared, generic (Button, Modal)
  features/
    invoices/
      InvoiceList.tsx
      InvoiceList.test.tsx
      useInvoices.ts
      types.ts
  lib/             # api client, helpers
  pages/           # or app/ for react-router
  main.tsx
```

Keep feature code colocated. Don't create parallel `tests/` trees — tests sit next to the code.

## 12. Checklist

- [ ] `tsc --noEmit` clean
- [ ] `eslint` clean (with `react-hooks` + `jsx-a11y`)
- [ ] Vitest/RTL tests green
- [ ] No `any`, no `// @ts-ignore`
- [ ] No data fetching in `useEffect` for production data
