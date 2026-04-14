/**
 * TanStack Query hook for GET /prompts. Server state lives here, not in
 * useState — per rules/react/coding-standards.md §3.4.
 *
 * Authored by `react-dev` in GREEN phase for PromptList.test.tsx.
 */
import { useQuery } from '@tanstack/react-query';

import type { PromptListItem } from './types';

type UseListPromptsResult = {
  data: PromptListItem[] | undefined;
  isLoading: boolean;
  isError: boolean;
};

async function fetchPrompts(): Promise<PromptListItem[]> {
  const res = await fetch('/api/prompts');
  if (!res.ok) {
    throw new Error(`GET /prompts -> ${res.status}`);
  }
  return (await res.json()) as PromptListItem[];
}

/** Return the current list of non-deleted prompts for list-view rendering. */
export function useListPrompts(): UseListPromptsResult {
  const q = useQuery({
    queryKey: ['prompts'],
    queryFn: fetchPrompts,
    staleTime: 30_000,
  });
  return {
    data: q.data,
    isLoading: q.isLoading,
    isError: q.isError,
  };
}
