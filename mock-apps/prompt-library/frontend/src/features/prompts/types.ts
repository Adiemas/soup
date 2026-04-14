/**
 * Shared frontend types for the prompt-library feature. Mirrors the
 * backend Pydantic response models in src/prompt_library/api/prompts.py.
 * Per rules/react/coding-standards.md §1.4 — no `any`, explicit types.
 */
export type Prompt = {
  id: string;
  title: string;
  body: string;
  tags: string[];
  approved: boolean;
  updatedAt: string; // ISO timestamp
};

export type PromptListItem = Pick<
  Prompt,
  'id' | 'title' | 'approved' | 'updatedAt'
>;
