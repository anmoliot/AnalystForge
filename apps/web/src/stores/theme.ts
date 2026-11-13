import { create } from "zustand";

export type Theme = "dark" | "light";

function initialTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function apply(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("af-theme", theme);
}

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggle: () => void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: initialTheme(),
  setTheme: (theme) => {
    apply(theme);
    set({ theme });
  },
  toggle: () => {
    const next: Theme = get().theme === "dark" ? "light" : "dark";
    apply(next);
    set({ theme: next });
  },
}));
