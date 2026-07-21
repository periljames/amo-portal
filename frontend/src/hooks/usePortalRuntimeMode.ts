import { useEffect, useState } from "react";
import { getPortalDataMode, isPortalDemoMode, isPortalGoLive, PORTAL_RUNTIME_MODE_EVENT, type PortalDataMode } from "../services/runtimeMode";

export function usePortalRuntimeMode() {
  const [isGoLive, setIsGoLive] = useState<boolean>(() => isPortalGoLive());
  const [isDemoMode, setIsDemoMode] = useState<boolean>(() => isPortalDemoMode());
  const [dataMode, setDataMode] = useState<PortalDataMode>(() => getPortalDataMode());

  useEffect(() => {
    const handleRuntimeModeChange = () => {
      setIsGoLive(isPortalGoLive());
      setIsDemoMode(isPortalDemoMode());
      setDataMode(getPortalDataMode());
    };

    window.addEventListener(PORTAL_RUNTIME_MODE_EVENT, handleRuntimeModeChange);
    return () => {
      window.removeEventListener(PORTAL_RUNTIME_MODE_EVENT, handleRuntimeModeChange);
    };
  }, []);

  return {
    isGoLive,
    isDemoMode,
    dataMode,
  };
}
