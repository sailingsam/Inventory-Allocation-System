"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, clearTokens, getAccess, setTokens } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<string | null>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // On mount, if we hold a token, hydrate the current user.
  useEffect(() => {
    (async () => {
      if (getAccess()) {
        const res = await api<User>("/me/");
        if (res.ok) setUser(res.data);
        else clearTokens();
      }
      setLoading(false);
    })();
  }, []);

  async function login(email: string, password: string): Promise<string | null> {
    const res = await api<{ access: string; refresh: string; user: User }>("/auth/login/", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) return "Invalid email or password.";
    setTokens(res.data.access, res.data.refresh);
    setUser(res.data.user);
    return null;
  }

  async function logout() {
    const refresh = localStorage.getItem("oms_refresh");
    if (refresh) await api("/auth/logout/", { method: "POST", body: JSON.stringify({ refresh }) });
    clearTokens();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
