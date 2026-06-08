import {
  createClient,
  type SupabaseClient,
} from "@supabase/supabase-js";

const supabaseConfig = {
  url: process.env.NEXT_PUBLIC_SUPABASE_URL,
  anonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
};

let browserClient: SupabaseClient | null = null;

export function isSupabaseConfigured() {
  return (
    Boolean(supabaseConfig.url) &&
    Boolean(supabaseConfig.anonKey)
  );
}

export function getSupabaseBrowserClient(): SupabaseClient {
  if (!isSupabaseConfigured()) {
    throw new Error("Supabase client environment variables are not configured.");
  }

  if (!browserClient) {
    browserClient = createClient(
      supabaseConfig.url as string,
      supabaseConfig.anonKey as string,
      {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true,
        },
      }
    );
  }

  return browserClient;
}
