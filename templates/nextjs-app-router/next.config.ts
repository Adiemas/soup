import type { NextConfig } from "next";

/**
 * Next.js config. TypeScript-first (Next 15+ supports `next.config.ts`).
 *
 * Keep this minimal. Do not sprinkle feature flags here; prefer env vars
 * or per-route exports (`dynamic`, `revalidate`, `runtime`).
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Server Components are the default. Client components opt-in via "use client".
  experimental: {
    // Document any experimental knob the team turns on here, with a dated reason.
  },
};

export default nextConfig;
