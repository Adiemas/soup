/**
 * <PromptList /> — GREEN phase component that satisfies PromptList.test.tsx.
 * Authored by `react-dev` per rules/react/coding-standards.md.
 *
 * - Functional component with explicit prop types (none here).
 * - Semantic <ul>/<li> (no role hacks per §8.1).
 * - Server state via useListPrompts() — no fetch in component body.
 * - Empty state is role="status" (aria-live by default) for screen readers.
 */
import { useListPrompts } from './useListPrompts';

export function PromptList(): JSX.Element {
  const { data, isLoading, isError } = useListPrompts();

  if (isLoading) {
    return <div role="status">Loading prompts...</div>;
  }
  if (isError) {
    return <div role="alert">Failed to load prompts.</div>;
  }
  const prompts = data ?? [];
  if (prompts.length === 0) {
    return <div role="status">No prompts yet. Add one to get started.</div>;
  }

  return (
    <ul aria-label="Prompt library">
      {prompts.map((p) => (
        <li key={p.id}>
          <span>{p.title}</span>
          {!p.approved && (
            <span aria-label="draft" className="ml-2 text-xs uppercase">
              Draft
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
