import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { ApiError, api, getToken, setToken } from "./api";
import type { Me } from "./types";

interface AuthValue {
  me: Me | null;
  loading: boolean;
  error: ApiError | null;
  hasToken: boolean;
  login: (email: string, name?: string) => Promise<void>;
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

  const login = useCallback(
    async (email: string, name?: string) => {
      const { access_token } = await api.devLogin(email, name);
      setToken(access_token);
      setHasToken(true);
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(() => {
    setToken(null);
    setHasToken(false);
    setMe(null);
    setError(null);
  }, []);

  useEffect(() => {
    void refresh();
    const onUnauthorized = () => {
      setHasToken(false);
      setMe(null);
    };
    window.addEventListener("ccr:unauthorized", onUnauthorized);
    return () => window.removeEventListener("ccr:unauthorized", onUnauthorized);
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ me, loading, error, hasToken, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
