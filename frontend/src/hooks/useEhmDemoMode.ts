// src/hooks/useEhmDemoMode.ts
import { useEffect, useState } from "react";
import { getCachedUser } from "../services/auth";
import { getAdminContext, setAdminContext } from "../services/adminUsers";
import { isPortalGoLive, PORTAL_RUNTIME_MODE_EVENT } from "../services/runtimeMode";

export function useEhmDemoMode() {
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [canToggleDemo, setCanToggleDemo] = useState(false);
  const [activeAmoId, setActiveAmoId] = useState<string | null>(null);
  const [goLiveLocked, setGoLiveLocked] = useState<boolean>(() => isPortalGoLive());

  useEffect(() => {
    const user = getCachedUser();
    const isSuperuser = !!user?.is_superuser || user?.role === "SUPERUSER";
    const locked = isPortalGoLive();
    setGoLiveLocked(locked);
    setCanToggleDemo(isSuperuser && !locked);
    if (!isSuperuser || locked) {
      setIsDemoMode(false);
      return;
    }
    const loadContext = async () => {
      try {
        const ctx = await getAdminContext();
        setIsDemoMode(ctx.data_mode === "DEMO");
        setActiveAmoId(ctx.active_amo_id);
      } catch {
        setIsDemoMode(false);
      }
    };
    loadContext();

    const onRuntimeModeChange = () => {
      const locked = isPortalGoLive();
      setGoLiveLocked(locked);
      setCanToggleDemo(isSuperuser && !locked);
      if (locked) setIsDemoMode(false);
    };

    window.addEventListener(PORTAL_RUNTIME_MODE_EVENT, onRuntimeModeChange);
    return () => window.removeEventListener(PORTAL_RUNTIME_MODE_EVENT, onRuntimeModeChange);
  }, []);

  const setDemoMode = (next: boolean) => {
    if (!canToggleDemo || goLiveLocked) return;
    const dataMode = next ? "DEMO" : "REAL";
    setAdminContext({
      data_mode: dataMode,
      active_amo_id: activeAmoId ?? undefined,
    })
      .then((ctx) => {
        setIsDemoMode(ctx.data_mode === "DEMO");
        setActiveAmoId(ctx.active_amo_id);
      })
      .catch(() => {
        setIsDemoMode(false);
      });
  };

  return {
    isDemoMode,
    canToggleDemo,
    goLiveLocked,
    setDemoMode,
  };
}
