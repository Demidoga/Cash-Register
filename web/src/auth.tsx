import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { ApiError, api, getToken, setToken } from "./api";
import { supabase, supabaseEnabled } from "./supabase";
import type { Me } from "./types";

interface AuthValue {
  me: Me | null;
  loading: boolean;
  error: ApiError | null;
  hasToken: boolean;
  supabaseEnabled: boolean;
  // Supabase-backed sign-in (production).
  signInWithGoogle: () => Promise<void>;
  signInWithPassword: (email: string, password: string) => Promise<void>;
  signUpWithPassword: (email: string, password: string, name?: string) => Promise<void>;
  // Dev fallback when Supabase is not configured.
  devLogin: (email: string, name?: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState<boolean>(!!getToken());
  const [error, setError] = useState<ApiError | null>(null);
  const [hasToken, setHasToken] = useState<boolean>(!!getToken());

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setMe(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      setMe(await api.me());
      setError(null);
    } catch (err) {
      setMe(null);
      setError(err instanceof ApiError ? err : new ApiError(0, String(err)));
    } finally {
      setLoading(false);
    }
  }, []);

  // --- Supabase session → API token sync ------------------------------------
  // The API client (api.ts) reads the bearer token from localStorage. Mirror
  // the Supabase access token there on every auth-state change (initial load,
  // sign-in, and silent token refresh) so requests, the offline queue, and
  // downloads all keep working without touching api.ts.
  useEffect(() => {
    if (!supabase) return;
    const apply = (token: string | null) => {
      setToken(token);
      setHasToken(!!token);
    };

    supabase.auth.getSession().then(({ data }) => {
      apply(data.session?.access_token ?? null);
      void refresh();
    });

    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      apply(session?.access_token ?? null);
      void refresh();
    });

    // api.ts drops the mirrored bearer on any 401 (it fires ccr:unauthorized).
    // The Supabase session is usually still valid or refreshable, so recover the
    // token rather than stranding the user on a dead page (which previously fell
    // through to the Setup screen): force one refresh and re-mirror, signing out
    // only if that genuinely fails. The 5s gate prevents a tight loop if the
    // backend rejects every token.
    let lastRecover = 0;
    const onUnauthorized = async () => {
      const now = Date.now();
      if (now - lastRecover < 5000) {
        apply(null);
        setMe(null);
        return;
      }
      lastRecover = now;
      const { data, error: refreshError } = await supabase!.auth.refreshSession();
      if (refreshError || !data.session) {
        apply(null);
        setMe(null);
      } else {
        apply(data.session.access_token);
        void refresh();
      }
    };
    window.addEventListener("ccr:unauthorized", onUnauthorized);

    return () => {
      sub.subscription.unsubscribe();
      window.removeEventListener("ccr:unauthorized", onUnauthorized);
    };
  }, [refresh]);

  // --- Dev fallback path (no Supabase configured) ---------------------------
  useEffect(() => {
    if (supabaseEnabled) return;
    void refresh();
    const onUnauthorized = () => {
      setHasToken(false);
      setMe(null);
    };
    window.addEventListener("ccr:unauthorized", onUnauthorized);
    return () => window.removeEventListener("ccr:unauthorized", onUnauthorized);
  }, [refresh]);

  const signInWithGoogle = useCallback(async () => {
    if (!supabase) throw new Error("Supabase is not configured");
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      // Come back to where we started after Google confirms the user.
      options: { redirectTo: window.location.origin },
    });
    if (error) throw new Error(error.message);
    // Browser redirects to Google here; the rest happens on return via
    // onAuthStateChange.
  }, []);

  const signInWithPassword = useCallback(async (email: string, password: string) => {
    if (!supabase) throw new Error("Supabase is not configured");
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw new Error(error.message);
  }, []);

  const signUpWithPassword = useCallback(
    async (email: string, password: string, name?: string) => {
      if (!supabase) throw new Error("Supabase is not configured");
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: name ? { data: { full_name: name } } : undefined,
      });
      if (error) throw new Error(error.message);
    },
    [],
  );

  const devLogin = useCallback(
    async (email: string, name?: string) => {
      const { access_token } = await api.devLogin(email, name);
      setToken(access_token);
      setHasToken(true);
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(() => {
    if (supabase) void supabase.auth.signOut();
    setToken(null);
    setHasToken(false);
    setMe(null);
    setError(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        me,
        loading,
        error,
        hasToken,
        supabaseEnabled,
        signInWithGoogle,
        signInWithPassword,
        signUpWithPassword,
        devLogin,
        logout,
        refresh,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
