import { useEffect, useState } from "react";
import { isPortalGoLive, PORTAL_RUNTIME_MODE_EVENT } from "../services/runtimeMode";

export function usePortalRuntimeMode() {
  const [isGoLive, setIsGoLive] = useState<boolean>(() => isPortalGoLive());

  useEffect(() => {
    const handleRuntimeModeChange = () => {
      setIsGoLive(isPortalGoLive());
    };

    window.addEventListener(PORTAL_RUNTIME_MODE_EVENT, handleRuntimeModeChange);
    return () => {
      window.removeEventListener(PORTAL_RUNTIME_MODE_EVENT, handleRuntimeModeChange);
    };
  }, []);

  return {
    isGoLive,
  };
}
