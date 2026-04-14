/**
 * RED-phase test for <PromptList />. Written by `test-engineer` under
 * /implement wave 1. Asserts the component renders titles, shows an empty
 * state, and surfaces the draft badge when approved=false. Fails until
 * `react-dev` writes PromptList.tsx + useListPrompts.ts.
 *
 * See specs/prompt-library-2026-04-14.md REQ-6 (draft indicator).
 * Per rules/react/coding-standards.md §9 — test behavior, not implementation.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PromptList } from './PromptList';
import * as hook from './useListPrompts';

type Prompt = {
  id: string;
  title: string;
  approved: boolean;
};

const make = (overrides: Partial<Prompt> = {}): Prompt => ({
  id: 'p-1',
  title: 'Invoice summary template',
  approved: true,
  ...overrides,
});

describe('<PromptList />', () => {
  it('renders a list item per prompt, keyed by id', () => {
    vi.spyOn(hook, 'useListPrompts').mockReturnValue({
      data: [make({ id: 'p-1', title: 'Alpha' }), make({ id: 'p-2', title: 'Beta' })],
      isLoading: false,
      isError: false,
    });

    render(<PromptList />);
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('Alpha');
    expect(items[1]).toHaveTextContent('Beta');
  });

  it('shows a draft badge when a prompt has no approved version', () => {
    vi.spyOn(hook, 'useListPrompts').mockReturnValue({
      data: [make({ id: 'p-3', title: 'Draft prompt', approved: false })],
      isLoading: false,
      isError: false,
    });

    render(<PromptList />);
    expect(screen.getByText(/draft/i)).toBeInTheDocument();
  });

  it('shows an empty state when there are no prompts', () => {
    vi.spyOn(hook, 'useListPrompts').mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });

    render(<PromptList />);
    expect(screen.getByRole('status')).toHaveTextContent(/no prompts/i);
  });
});
