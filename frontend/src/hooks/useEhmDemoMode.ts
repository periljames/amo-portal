// src/hooks/useEhmDemoMode.ts
import { useEffect, useState } from "react";
import { getCachedUser } from "../services/auth";
import { getAdminContext, setAdminContext } from "../services/adminUsers";

export function useEhmDemoMode() {
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [canToggleDemo, setCanToggleDemo] = useState(false);
  const [activeAmoId, setActiveAmoId] = useState<string | null>(null);

  useEffect(() => {
    const user = getCachedUser();
    const isSuperuser = !!user?.is_superuser || user?.role === "SUPERUSER";
    setCanToggleDemo(isSuperuser);
    if (!isSuperuser) {
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
  }, []);

  const setDemoMode = (next: boolean) => {
    if (!canToggleDemo) return;
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
    setDemoMode,
  };
}
