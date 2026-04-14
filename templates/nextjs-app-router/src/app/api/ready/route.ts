import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * Readiness probe — Supabase reachable + auth cookie refresh works.
 *
 * Distinct from `/api/health/` which is a liveness check only. This
 * handler pings Supabase (via a cheap RPC or a trivial query) and
 * returns `{ status: "degraded" }` with HTTP 503 when the backend
 * is unreachable. Deploy targets (Vercel, K8s) should probe this
 * endpoint before routing traffic to the instance.
 *
 * See `rules/observability/health-readiness.md` for the contract.
 */
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const started = Date.now();
  try {
    const supabase = await createClient();
    // Cheap round-trip: select now(). Any schema error -> degraded.
    const { error } = await supabase.rpc("ready_check").limit(1);
    if (error) {
      // Fall back to a schema-free ping.
      const { error: pingErr } = await supabase.auth.getSession();
      if (pingErr) throw pingErr;
    }
    return NextResponse.json({
      status: "ready",
      checks: {
        supabase: { ok: true, latency_ms: Date.now() - started },
      },
    });
  } catch (err) {
    return NextResponse.json(
      {
        status: "degraded",
        checks: {
          supabase: {
            ok: false,
            error: err instanceof Error ? err.message : "unknown",
          },
        },
      },
      { status: 503 },
    );
  }
}
