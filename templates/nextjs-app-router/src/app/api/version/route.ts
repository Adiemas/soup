import { NextResponse } from "next/server";

/**
 * Build-identity endpoint. Returns the commit SHA + build timestamp
 * set by the deploy pipeline. No dep calls; pure env lookups.
 *
 * - `git_sha` — set by Vercel (`VERCEL_GIT_COMMIT_SHA`), GitHub
 *   Actions (`GITHUB_SHA`), or a generic `GIT_SHA`. Falls back to
 *   "dev" when unset.
 * - `build_time` — ISO-8601 UTC timestamp. The deploy pipeline should
 *   inject this; falls back to module-load time.
 * - `env` — `APP_ENV` (prod / staging / dev).
 *
 * See `rules/observability/health-readiness.md` for the contract.
 */
export const dynamic = "force-static";
export const runtime = "edge";

const BUILD_TIME_FALLBACK = new Date().toISOString();

export function GET() {
  return NextResponse.json({
    service: "your-app",
    git_sha:
      process.env.VERCEL_GIT_COMMIT_SHA ??
      process.env.GITHUB_SHA ??
      process.env.GIT_SHA ??
      "dev",
    build_time: process.env.BUILD_TIME ?? BUILD_TIME_FALLBACK,
    env: process.env.APP_ENV ?? process.env.NODE_ENV ?? "dev",
  });
}
