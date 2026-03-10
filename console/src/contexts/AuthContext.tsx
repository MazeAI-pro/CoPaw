import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  fetchSupabaseConfig,
  getSupabaseSession,
  initSupabase,
  isSupabaseEnabled,
  onSupabaseAuthStateChange,
  signInWithEmail,
  signOutSupabase,
} from "../lib/supabase";
import {
  setTokenGetter,
  setUnauthorizedHandler,
} from "../api/request";

type AuthMode = "legacy" | "supabase";

type AuthUser = {
  id: string;
  email?: string;
  mode: AuthMode;
};

type AuthStatus = {
  authenticated: boolean;
  user_id?: string | null;
  auth_mode?: AuthMode | "disabled" | null;
};

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  supabaseEnabled: boolean;
  loginWithCredentials: (username: string, password: string) => Promise<void>;
  loginWithSupabase: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

async function fetchAuthStatus(): Promise<AuthStatus> {
  const response = await fetch("/api/auth/status");
  if (!response.ok) {
    return { authenticated: false };
  }
  return (await response.json()) as AuthStatus;
}

function updateWindowUserId(user: AuthUser | null): void {
  (window as Window & { currentUserId?: string }).currentUserId = user?.id || "default";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [supabaseEnabled, setSupabaseEnabled] = useState(false);

  useEffect(() => {
    let mounted = true;
    let unsubscribe = () => {};

    const initialize = async () => {
      try {
        const cfg = await fetchSupabaseConfig();
        const hasSupabaseConfig = Boolean(cfg.supabaseUrl && cfg.supabaseAnonKey);
        if (hasSupabaseConfig) {
          initSupabase(cfg.supabaseUrl!, cfg.supabaseAnonKey!);
        }
        if (!mounted) {
          return;
        }
        setSupabaseEnabled(hasSupabaseConfig);

        setTokenGetter(async () => {
          if (!isSupabaseEnabled()) {
            return null;
          }
          const session = await getSupabaseSession();
          return session?.access_token ?? null;
        });
        setUnauthorizedHandler(() => {
          setUser(null);
          updateWindowUserId(null);
        });

        const [status, supabaseSession] = await Promise.all([
          fetchAuthStatus(),
          hasSupabaseConfig ? getSupabaseSession() : Promise.resolve(null),
        ]);
        if (!mounted) {
          return;
        }

        if (supabaseSession?.user?.id) {
          setUser({
            id: supabaseSession.user.id,
            email: supabaseSession.user.email || undefined,
            mode: "supabase",
          });
        } else if (status.authenticated && status.user_id) {
          setUser({
            id: status.user_id,
            mode: status.auth_mode === "supabase" ? "supabase" : "legacy",
          });
        } else {
          setUser(null);
        }

        if (hasSupabaseConfig) {
          const sub = onSupabaseAuthStateChange((_event, session) => {
            if (!mounted) {
              return;
            }
            if (session?.user?.id) {
              setUser({
                id: session.user.id,
                email: session.user.email || undefined,
                mode: "supabase",
              });
            } else {
              setUser((prev) => (prev?.mode === "supabase" ? null : prev));
            }
          });
          unsubscribe = sub.unsubscribe;
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    initialize();

    return () => {
      mounted = false;
      unsubscribe();
      setUnauthorizedHandler(null);
    };
  }, []);

  useEffect(() => {
    updateWindowUserId(user);
  }, [user]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      supabaseEnabled,
      async loginWithCredentials(username: string, password: string) {
        const response = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || "Login failed");
        }
        const status = await fetchAuthStatus();
        setUser({
          id: status.user_id || "default",
          mode: "legacy",
        });
      },
      async loginWithSupabase(email: string, password: string) {
        if (!supabaseEnabled) {
          throw new Error("Supabase is not enabled");
        }
        const { data, error } = await signInWithEmail(email, password);
        if (error) {
          throw new Error(error.message || "Supabase login failed");
        }
        if (!data.user) {
          throw new Error("Supabase login failed");
        }
        setUser({
          id: data.user.id,
          email: data.user.email || undefined,
          mode: "supabase",
        });
      },
      async signOut() {
        if (user?.mode === "supabase") {
          await signOutSupabase();
        }
        await fetch("/api/auth/logout", { method: "POST" });
        setUser(null);
      },
    }),
    [loading, supabaseEnabled, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
