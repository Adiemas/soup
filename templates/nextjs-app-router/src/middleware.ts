import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Routing Middleware. Runs before cache on every request matching `config.matcher`.
 *
 * Use cases: auth redirects, geo routing, A/B cookie stamping, rewrites.
 *
 * Keep this lean. A slow middleware blocks every request. Do NOT call
 * slow APIs here; the middleware has a strict execution budget.
 *
 * For Supabase auth cookie refresh in App Router, see
 *   rules/supabase/client-and-migrations.md § "Middleware for session refresh"
 * and swap the stub below for the @supabase/ssr pattern when auth lands.
 */
export function middleware(request: NextRequest) {
  // Example: attach a request id for correlation in structured logs.
  const requestId = crypto.randomUUID();
  const response = NextResponse.next();
  response.headers.set("x-request-id", requestId);
  return response;
}

export const config = {
  // Exclude static assets. Tune when adding authenticated routes.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
