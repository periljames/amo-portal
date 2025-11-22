// src/hooks/useColorScheme.ts
import { useEffect, useState } from "react";

export type ColorScheme = "dark" | "light";

const STORAGE_KEY = "amo_color_scheme";

export function useColorScheme() {
  const [scheme, setScheme] = useState<ColorScheme>(() => {
    if (typeof window === "undefined") return "dark";
    const saved = window.localStorage.getItem(STORAGE_KEY) as ColorScheme | null;
    return saved === "light" || saved === "dark" ? saved : "dark";
  });

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.dataset.colorScheme = scheme;
    window.localStorage.setItem(STORAGE_KEY, scheme);
  }, [scheme]);

  const toggle = () =>
    setScheme((prev) => (prev === "dark" ? "light" : "dark"));

  return { scheme, toggle };
}
