import { useCallback, useEffect, useRef, useState } from "react";

import { PLATFORM_CONSOLE_LIVE_EVENT } from "./usePlatformRealtime";

type PlatformDataOptions = {
  pollMs?: number;
  live?: boolean;
};

export function usePlatformData<T>(
  loader: () => Promise<T>,
  deps: unknown[] = [],
  options: PlatformDataOptions = {},
) {
  const { pollMs = 30_000, live = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const requestIdRef = useRef(0);
  const liveDebounceRef = useRef<number | null>(null);

  const execute = useCallback((showLoading = true) => {
    const requestId = ++requestIdRef.current;
    if (showLoading) setLoading(true);
    setError(null);
    return loader()
      .then((value) => {
        if (requestId !== requestIdRef.current) return value;
        setData(value);
        setLastUpdated(new Date());
        return value;
      })
      .catch((nextError) => {
        if (requestId === requestIdRef.current) setError(nextError);
        throw nextError;
      })
      .finally(() => {
        if (requestId === requestIdRef.current) setLoading(false);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const reload = useCallback(() => {
    void execute(data === null).catch(() => undefined);
  }, [data, execute]);

  useEffect(() => {
    void execute(true).catch(() => undefined);
  }, [execute]);

  useEffect(() => {
    if (!pollMs || pollMs < 5_000) return;
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void execute(false).catch(() => undefined);
    }, pollMs);
    return () => window.clearInterval(interval);
  }, [execute, pollMs]);

  useEffect(() => {
    const refreshVisible = () => {
      if (document.visibilityState === "visible") void execute(false).catch(() => undefined);
    };
    window.addEventListener("focus", refreshVisible);
    document.addEventListener("visibilitychange", refreshVisible);
    return () => {
      window.removeEventListener("focus", refreshVisible);
      document.removeEventListener("visibilitychange", refreshVisible);
    };
  }, [execute]);

  useEffect(() => {
    if (!live) return;
    const handleLiveEvent = () => {
      if (document.visibilityState !== "visible") return;
      if (liveDebounceRef.current) window.clearTimeout(liveDebounceRef.current);
      liveDebounceRef.current = window.setTimeout(() => {
        void execute(false).catch(() => undefined);
      }, 350);
    };
    window.addEventListener(PLATFORM_CONSOLE_LIVE_EVENT, handleLiveEvent);
    return () => {
      window.removeEventListener(PLATFORM_CONSOLE_LIVE_EVENT, handleLiveEvent);
      if (liveDebounceRef.current) window.clearTimeout(liveDebounceRef.current);
    };
  }, [execute, live]);

  return { data, loading, error, reload, lastUpdated };
}
