import {
  createClient,
  type SupabaseClient,
  type Session,
  type AuthChangeEvent,
} from "@supabase/supabase-js";

let supabaseClient: SupabaseClient | null = null;
let supabaseEnabled = false;

export async function fetchSupabaseConfig(): Promise<{
  supabaseUrl: string | null;
  supabaseAnonKey: string | null;
}> {
  const response = await fetch("/api/auth/supabase-config");
  if (!response.ok) {
    return { supabaseUrl: null, supabaseAnonKey: null };
  }
  const data = (await response.json()) as {
    supabase_url?: string | null;
    supabase_anon_key?: string | null;
  };
  return {
    supabaseUrl: data.supabase_url ?? null,
    supabaseAnonKey: data.supabase_anon_key ?? null,
  };
}

export function initSupabase(url: string, anonKey: string): void {
  if (!supabaseClient) {
    supabaseClient = createClient(url, anonKey);
  }
  supabaseEnabled = true;
}

export function isSupabaseEnabled(): boolean {
  return supabaseEnabled;
}

export function getSupabase(): SupabaseClient {
  if (!supabaseClient) {
    throw new Error("Supabase is not initialized");
  }
  return supabaseClient;
}

export async function getSupabaseSession() {
  if (!supabaseClient) {
    return null;
  }
  const {
    data: { session },
  } = await supabaseClient.auth.getSession();
  return session;
}

export async function signInWithEmail(email: string, password: string) {
  return getSupabase().auth.signInWithPassword({ email, password });
}

export async function signOutSupabase() {
  if (!supabaseClient) {
    return;
  }
  await supabaseClient.auth.signOut();
}

export function onSupabaseAuthStateChange(
  callback: (event: AuthChangeEvent, session: Session | null) => void,
) {
  if (!supabaseClient) {
    return { unsubscribe: () => {} };
  }
  const {
    data: { subscription },
  } = supabaseClient.auth.onAuthStateChange((event, session) => {
    callback(event, session);
  });
  return {
    unsubscribe: () => subscription.unsubscribe(),
  };
}
