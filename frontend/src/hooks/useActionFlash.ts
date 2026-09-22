import { useCallback, useEffect, useRef, useState } from "react";

const DEFAULT_ACTION_FLASH_MS = 2200;

/**
 * Brief success flash for the control that was just activated.
 * Prefer this over persistent full-width success banners.
 */
export function useActionFlash(durationMs = DEFAULT_ACTION_FLASH_MS) {
  const [actionFlash, setActionFlash] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const clearActionFlash = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setActionFlash(null);
  }, []);

  const flashAction = useCallback((key: string) => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    setActionFlash(key);
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      setActionFlash(null);
    }, Math.max(800, durationMs));
  }, [durationMs]);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
  }, []);

  return { actionFlash, flashAction, clearActionFlash };
}

export function isActionFlashing(actionFlash: string | null, key: string): boolean {
  return actionFlash === key;
}
