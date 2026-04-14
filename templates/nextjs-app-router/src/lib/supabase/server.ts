import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/**
 * Server-side Supabase client bound to the current Request's cookies.
 *
 * Use in:
 *   - Server Components
 *   - Route Handlers (app/api/*)
 *   - Server Actions
 *
 * Never expose `SUPABASE_SERVICE_ROLE_KEY` to this client — it uses the
 * anon key and relies on RLS + the signed-in user's JWT. For background
 * jobs that must bypass RLS, build a separate admin client in a
 * non-request context and never ship it to `"use client"` code.
 *
 * Env vars required:
 *   NEXT_PUBLIC_SUPABASE_URL
 *   NEXT_PUBLIC_SUPABASE_ANON_KEY
 */
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            );
          } catch {
            // `setAll` will throw from a Server Component — that is fine IF
            // middleware is refreshing sessions. See rules/supabase/*.md.
          }
        },
      },
    }
  );
}
