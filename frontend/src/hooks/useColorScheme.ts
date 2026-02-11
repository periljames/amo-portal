// src/hooks/useColorScheme.ts
import { useEffect, useState } from "react";

export type ColorScheme = "dark" | "light" | "system";
export type ResolvedColorScheme = "dark" | "light";

const STORAGE_KEY = "amo_color_scheme";

const resolveSystemScheme = (): ResolvedColorScheme => {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
};

export function useColorScheme() {
  const [scheme, setScheme] = useState<ColorScheme>(() => {
    if (typeof window === "undefined") return "dark";
    const saved = window.localStorage.getItem(STORAGE_KEY) as ColorScheme | null;
    return saved === "light" || saved === "dark" || saved === "system" ? saved : "system";
  });

  const [resolvedScheme, setResolvedScheme] = useState<ResolvedColorScheme>(() =>
    scheme === "system" ? resolveSystemScheme() : scheme,
  );

  useEffect(() => {
    if (scheme !== "system") {
      setResolvedScheme(scheme);
      return;
    }

    const media = window.matchMedia("(prefers-color-scheme: light)");
    const apply = () => setResolvedScheme(media.matches ? "light" : "dark");
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [scheme]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.dataset.colorScheme = resolvedScheme;
    document.body.dataset.colorSchemeMode = scheme;
    window.localStorage.setItem(STORAGE_KEY, scheme);
  }, [resolvedScheme, scheme]);

  const toggle = () =>
    setScheme((prev) => {
      if (prev === "dark") return "light";
      if (prev === "light") return "system";
      return "dark";
    });

  return { scheme, resolvedScheme, setScheme, toggle };
}
