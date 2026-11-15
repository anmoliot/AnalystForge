import { create } from "zustand";

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  role: "ADMIN" | "PORTFOLIO_MANAGER" | "ANALYST" | "READ_ONLY";
  tenant_id: string;
  tenant_name?: string;
  totp_enabled?: boolean;
}

interface AuthState {
  token: string | null;
  user: UserProfile | null;
  isAuthenticated: boolean;
  setAuth: (token: string, user: UserProfile) => void;
  logout: () => void;
  init: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  token: typeof localStorage !== "undefined" ? localStorage.getItem("af-token") : null,
  user:
    typeof localStorage !== "undefined" && localStorage.getItem("af-user")
      ? JSON.parse(localStorage.getItem("af-user") || "null")
      : null,
  isAuthenticated:
    typeof localStorage !== "undefined" ? Boolean(localStorage.getItem("af-token")) : false,
  setAuth: (token, user) => {
    localStorage.setItem("af-token", token);
    localStorage.setItem("af-user", JSON.stringify(user));
    set({ token, user, isAuthenticated: true });
  },
  logout: () => {
    localStorage.removeItem("af-token");
    localStorage.removeItem("af-user");
    set({ token: null, user: null, isAuthenticated: false });
  },
  init: () => {
    const token = localStorage.getItem("af-token");
    const user = localStorage.getItem("af-user");
    if (token && user) {
      try {
        set({ token, user: JSON.parse(user), isAuthenticated: true });
      } catch {
        set({ token: null, user: null, isAuthenticated: false });
      }
    }
  },
}));
