import { useEffect, useState } from "react";

export type ColorScheme = "dark" | "light" | "system";
export type ResolvedColorScheme = "dark" | "light";
const STORAGE_KEY = "amo_color_scheme";
const CHANGE_EVENT = "amo:color-scheme-changed";
const preference = (value: unknown): ColorScheme => value === "light" || value === "dark" ? value : "system";
const resolveSystemScheme = (): ResolvedColorScheme => typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
function savedScheme(): ColorScheme {
  try { return typeof window === "undefined" ? "system" : preference(window.localStorage.getItem(STORAGE_KEY)); }
  catch { return "system"; }
}

export function useColorScheme() {
  const [scheme, setScheme] = useState<ColorScheme>(savedScheme);
  const [systemScheme, setSystemScheme] = useState<ResolvedColorScheme>(resolveSystemScheme);
  const resolvedScheme = scheme === "system" ? systemScheme : scheme;

  useEffect(() => {
    if (scheme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const apply = () => setSystemScheme(media.matches ? "light" : "dark");
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [scheme]);

  useEffect(() => {
    const onChange = (event: Event) => setScheme(preference((event as CustomEvent).detail));
    const onStorage = (event: StorageEvent) => { if (event.key === STORAGE_KEY || event.key === null) setScheme(preference(event.newValue)); };
    window.addEventListener(CHANGE_EVENT, onChange);
    window.addEventListener("storage", onStorage);
    return () => { window.removeEventListener(CHANGE_EVENT, onChange); window.removeEventListener("storage", onStorage); };
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.colorScheme = resolvedScheme;
    root.dataset.colorSchemeMode = scheme;
    root.style.colorScheme = resolvedScheme;
    document.body.dataset.colorScheme = resolvedScheme;
    document.body.dataset.colorSchemeMode = scheme;
    try { window.localStorage.setItem(STORAGE_KEY, scheme); } catch { /* Theme changes still work with blocked storage. */ }
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: scheme }));
  }, [resolvedScheme, scheme]);

  const toggle = () => setScheme((previous) => previous === "dark" ? "light" : previous === "light" ? "system" : "dark");
  return { scheme, resolvedScheme, setScheme, toggle };
}
