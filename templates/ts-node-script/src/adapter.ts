import { z } from "zod";

/**
 * Tiny adapter surface. A real script would have one adapter per source
 * kind (rss, api, html); this is the minimal shape the main entry depends
 * on so unit tests can verify the boundary without network.
 */

export const ItemSchema = z.object({
  id: z.string().min(1),
  source: z.string().min(1),
  title: z.string().min(1),
  url: z.string().url(),
  publishedAt: z.string().datetime().optional(),
});
export type Item = z.infer<typeof ItemSchema>;

export interface FetchInput {
  source: string;
  limit: number;
}

export interface FetchResult {
  items: Item[];
  fetchedAt: string;
}

/**
 * Reference implementation: returns deterministic fake items. Replace
 * with real sources (rss, API, html parse) in production. Keep the
 * contract stable so tests don't churn.
 */
export async function fetchAndSummarize(input: FetchInput): Promise<FetchResult> {
  const count = Math.max(0, Math.min(input.limit, 10));
  const items: Item[] = Array.from({ length: count }, (_, i) =>
    ItemSchema.parse({
      id: `${input.source}-${i + 1}`,
      source: input.source,
      title: `Item ${i + 1} from ${input.source}`,
      url: `https://example.invalid/${input.source}/${i + 1}`,
      publishedAt: new Date(0).toISOString(),
    })
  );
  return {
    items,
    fetchedAt: new Date(0).toISOString(),
  };
}
