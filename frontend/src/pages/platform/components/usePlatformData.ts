import { useCallback, useEffect, useMemo, useRef, useState } from "react";

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
  const inFlightRef = useRef<{ key: symbol; promise: Promise<T> } | null>(null);
  // A new key permits a new request immediately when the selected tenant,
  // environment or tab changes while still deduplicating poll/focus/live races.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const executionKey = useMemo(() => Symbol("platform-data-scope"), deps);

  const execute = useCallback((showLoading = true) => {
    const active = inFlightRef.current;
    if (active?.key === executionKey) return active.promise;

    const requestId = ++requestIdRef.current;
    if (showLoading) setLoading(true);
    setError(null);

    const promise = loader()
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
        if (inFlightRef.current?.promise === promise) inFlightRef.current = null;
        if (requestId === requestIdRef.current) setLoading(false);
      });

    inFlightRef.current = { key: executionKey, promise };
    return promise;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [executionKey, ...deps]);

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
