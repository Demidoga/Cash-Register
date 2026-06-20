// Supabase client — the real identity provider (ADR-0001). Supabase runs the
// Google OAuth flow and email/password auth, issues a JWT, and FastAPI verifies
// it (see api/app/security.py). The backend never sees a password.
//
// If the env vars are absent the client is null and the app falls back to the
// dev login, so the project still runs locally without a Supabase project.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const supabaseEnabled = Boolean(url && anonKey);

export const supabase: SupabaseClient | null = supabaseEnabled
  ? createClient(url!, anonKey!, {
      auth: {
        // Persist the session and refresh tokens automatically; pick up the
        // token Google hands back in the URL after the OAuth redirect.
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;
