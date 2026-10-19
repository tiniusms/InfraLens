import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ThemeContext, type ThemeName } from "./theme-context";

const STORAGE_KEY = "infralens-theme";

function initialTheme(): ThemeName {
  if (typeof document !== "undefined") {
    const existing = document.documentElement.dataset.theme;
    if (existing === "light" || existing === "dark") {
      return existing;
    }
  }
  if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  return "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeName>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Theme still applies for this view when storage is blocked.
    }
  }, [theme]);

  const value = useMemo(() => ({ theme, setTheme }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
