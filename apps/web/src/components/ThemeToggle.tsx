import { Moon, Sun } from "lucide-react";

import { useTheme } from "@/stores/theme";

export function ThemeToggle() {
  const theme = useTheme((state) => state.theme);
  const toggle = useTheme((state) => state.toggle);
  const nextLabel = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={nextLabel}
      title={nextLabel}
      className="flex size-7 items-center justify-center rounded text-muted transition-colors hover:bg-elevated hover:text-ink"
    >
      {theme === "dark" ? (
        <Sun className="size-4" aria-hidden="true" />
      ) : (
        <Moon className="size-4" aria-hidden="true" />
      )}
    </button>
  );
}
