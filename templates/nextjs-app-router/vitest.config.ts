import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

/**
 * Vitest config. jsdom env for component tests; excludes e2e tree so
 * Playwright tests never execute under Vitest.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/__tests__/setup.ts"],
    css: false,
    exclude: ["node_modules", "e2e", ".next", "dist"],
  },
});
