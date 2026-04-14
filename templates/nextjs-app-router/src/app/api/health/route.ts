import { NextResponse } from "next/server";

/**
 * Route Handler. Default is Node.js runtime. Override with:
 *   export const runtime = "edge";
 * when the handler does not need Node APIs.
 *
 * `dynamic = "force-static"` skips per-request execution (CDN cacheable).
 * Omit (default "auto") when the response may vary per request.
 */
export const dynamic = "force-static";

export function GET() {
  return NextResponse.json({ ok: true, service: "your-app" });
}
