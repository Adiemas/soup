import { describe, expect, it } from "vitest";
import { fetchAndSummarize, ItemSchema } from "./adapter.js";

describe("fetchAndSummarize", () => {
  it("returns up to `limit` items shaped per ItemSchema", async () => {
    const out = await fetchAndSummarize({ source: "test", limit: 3 });
    expect(out.items).toHaveLength(3);
    for (const it of out.items) {
      expect(() => ItemSchema.parse(it)).not.toThrow();
      expect(it.source).toBe("test");
    }
  });

  it("caps at 10 and returns the full fetchedAt timestamp", async () => {
    const out = await fetchAndSummarize({ source: "test", limit: 100 });
    expect(out.items).toHaveLength(10);
    expect(typeof out.fetchedAt).toBe("string");
    expect(Number.isNaN(Date.parse(out.fetchedAt))).toBe(false);
  });

  it("returns zero items when limit is 0", async () => {
    const out = await fetchAndSummarize({ source: "test", limit: 0 });
    expect(out.items).toHaveLength(0);
  });
});
