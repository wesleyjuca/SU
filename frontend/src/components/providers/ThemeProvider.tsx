"use client";
import { useEffect } from "react";
import { fetchAndApplyTheme, getStoredTheme, applyTheme } from "@/lib/theme";
import { useThemeStore } from "@/store";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const setTheme = useThemeStore((s) => s.setTheme);

  useEffect(() => {
    // Apply stored theme immediately (no flicker)
    const stored = getStoredTheme();
    if (stored) {
      applyTheme(stored);
      setTheme(stored);
    }

    // Then fetch latest from API
    fetchAndApplyTheme().then((theme) => {
      setTheme(theme);
    });
  }, [setTheme]);

  return <>{children}</>;
}
