// src/hooks/useEhmDemoMode.ts
import { useEffect, useState } from "react";
import { getCachedUser } from "../services/auth";

const DEMO_STORAGE_KEY = "ehm_demo_mode";

export function useEhmDemoMode() {
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [canToggleDemo, setCanToggleDemo] = useState(false);

  useEffect(() => {
    const user = getCachedUser();
    const isSuperuser = !!user?.is_superuser || user?.role === "SUPERUSER";
    setCanToggleDemo(isSuperuser);
    if (!isSuperuser) {
      setIsDemoMode(false);
      return;
    }
    const stored = window.localStorage.getItem(DEMO_STORAGE_KEY);
    setIsDemoMode(stored === "true");
  }, []);

  const setDemoMode = (next: boolean) => {
    if (!canToggleDemo) return;
    setIsDemoMode(next);
    window.localStorage.setItem(DEMO_STORAGE_KEY, String(next));
  };

  return {
    isDemoMode,
    canToggleDemo,
    setDemoMode,
  };
}
