"use client";

import { createBrowserClient } from "@supabase/ssr";

/**
 * Browser Supabase client. Call from "use client" components only.
 *
 * Uses the anon key. Browser code MUST NOT receive the service-role key.
 * Row-Level Security is the only thing standing between this client and
 * your database — keep RLS default-deny and test both the allowed and
 * forbidden paths.
 */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
