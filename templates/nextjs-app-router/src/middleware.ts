import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Routing Middleware — runs before cache on every request matching
 * `config.matcher`. Use for: auth redirects, geo routing, A/B cookie
 * stamping, rewrites, and the soup correlation-id contract.
 *
 * Keep this lean. A slow middleware blocks every request. Do NOT call
 * slow APIs here; the middleware has a strict execution budget.
 *
 * Correlation IDs (iter-3 ε6, see `rules/observability/correlation-
 * ids.md`): read `x-request-id` on every request; generate a UUID4
 * when absent; forward it to downstream handlers via the rewritten
 * request headers so Route Handlers + Server Components can read it;
 * mirror the final id on the response.
 *
 * For Supabase auth cookie refresh in App Router, see
 *   rules/supabase/client-and-migrations.md § "Middleware for session refresh"
 * and compose the `@supabase/ssr` pattern with the correlation-id logic
 * below when auth lands.
 */
export function middleware(request: NextRequest) {
  const incoming = request.headers.get("x-request-id");
  const correlationId = incoming ?? crypto.randomUUID();

  // Forward the correlation id to downstream handlers by rewriting the
  // incoming request headers. Route Handlers read it via `headers()`.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-request-id", correlationId);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("x-request-id", correlationId);
  return response;
}

export const config = {
  // Exclude static assets. Tune when adding authenticated routes.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
