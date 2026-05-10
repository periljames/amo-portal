import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { getApiBaseUrl } from "../../services/config";
import { getCachedUser, getContext, getToken, onSessionEvent } from "../../services/auth";
import { playNotificationChirp, pushDesktopNotification } from "../../services/notificationPreferences";
import { fetchHealthz, fetchServerTime, RealtimeHttpError } from "../../services/realtime/api";
import { RealtimeMqttClient } from "../../services/realtime/mqtt";
import type { BrokerState } from "../../services/realtime/types";
import { RealtimeContext } from "./realtimeContext";
import { isRealtimeEnabled } from "../../utils/featureFlags";

export type RealtimeStatus = "live" | "syncing" | "offline";
export type BackendHealth = "ok" | "degraded";

export type ActivityEvent = {
  id: string;
  type: string;
  entityType: string;
  entityId: string;
  action: string;
  timestamp: string;
  actor?: { userId?: string; name?: string; department?: string } | null;
  metadata?: Record<string, unknown>;
};


const eventSchema = z.object({
  id: z.string(),
  type: z.string(),
  entityType: z.string(),
  entityId: z.string(),
  action: z.string(),
  timestamp: z.string(),
  actor: z.object({ userId: z.string().optional(), name: z.string().optional(), department: z.string().optional() }).nullable().optional(),
  metadata: z.record(z.unknown()).optional(),
});

const MAX_ACTIVITY = 1500;

function isLoginSurface(): boolean {
  if (typeof window === "undefined") return false;
  return /\/login\/?$/.test(window.location.pathname);
}

type ParsedSseEvent = { event: string; data: string; id?: string };
function parseSseBlock(block: string): ParsedSseEvent | null {
  const lines = block.split(/\r?\n/);
  let event = "message";
  let id: string | undefined;
  const dataLines: string[] = [];
  for (const line of lines) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim() || "message";
    else if (line.startsWith("id:")) id = line.slice(3).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  return { event, data: dataLines.join("\n"), id };
}

export const RealtimeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<RealtimeStatus>("syncing");
  const [brokerState, setBrokerState] = useState<BrokerState>("offline");
  const [backendHealth, setBackendHealth] = useState<BackendHealth>("ok");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [currentTime, setCurrentTime] = useState<Date>(new Date());
  const [lastGoodServerTime, setLastGoodServerTime] = useState<Date | null>(null);
  const [lastClockSyncAt, setLastClockSyncAt] = useState<Date | null>(null);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const controllerRef = useRef<AbortController | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const connectRef = useRef<() => void>(() => undefined);
  const retryCount = useRef(0);
  const staleIntervalRef = useRef<number | null>(null);
  const [staleSeconds, setStaleSeconds] = useState(0);
  const [isOnline, setIsOnline] = useState<boolean>(typeof navigator === "undefined" ? true : navigator.onLine);
  const [clockSource, setClockSource] = useState<"server" | "local">("local");
  const clockOffsetMsRef = useRef(0);
  const frozenClockRef = useRef<number | null>(null);
  const mqttRef = useRef<RealtimeMqttClient | null>(null);
  const ctx = getContext();
  const cachedUser = getCachedUser();
  const isPlatformUser = Boolean(cachedUser?.is_superuser && !cachedUser?.amo_id);
  const lastEventKey = `amo:last-event-id:${ctx.amoCode || "unknown"}`;

  const isStale = !isOnline || (status === "offline" && !lastGoodServerTime);

  const serverNow = useCallback(() => {
    if (frozenClockRef.current !== null) return new Date(frozenClockRef.current);
    return new Date(Date.now() + clockOffsetMsRef.current);
  }, []);

  const syncServerTime = useCallback(async () => {
    try {
      const data = await fetchServerTime();
      clockOffsetMsRef.current = data.epoch_ms - Date.now();
      frozenClockRef.current = null;
      setClockSource("server");
      const syncedTime = new Date(data.epoch_ms);
      setLastGoodServerTime(syncedTime);
      setLastClockSyncAt(new Date());
      setCurrentTime(syncedTime);
      setStatus((prev) => (prev === "offline" ? "live" : prev));
    } catch {
      if (frozenClockRef.current === null) frozenClockRef.current = Date.now() + clockOffsetMsRef.current;
    }
  }, []);


  const sendPresenceHeartbeat = useCallback(async (state: "online" | "away" = "online") => {
    if (isPlatformUser || isLoginSurface()) return;
    const token = getToken();
    if (!token || !isRealtimeEnabled()) return;
    try {
      await fetch(`${getApiBaseUrl()}/api/realtime/presence`, {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ state }),
      });
    } catch {
      // presence is best-effort only
    }
  }, [isPlatformUser]);

  const handleEvent = useCallback((raw: unknown, transportCursor?: string) => {
    const parsed = eventSchema.safeParse(raw);
    if (!parsed.success) return;
    const event = parsed.data;
    const cursor = transportCursor?.trim() || event.id?.trim();
    if (!cursor) return;

    window.localStorage.setItem(lastEventKey, cursor);
    setStatus("live");
    setLastUpdated(new Date(Date.parse(event.timestamp) || Date.now()));
    setStaleSeconds(0);
    setActivity((prev) => [event, ...prev].slice(0, MAX_ACTIVITY));
    playNotificationChirp();
    void pushDesktopNotification("Realtime event", `${event.type} ${event.action}`);
    queryClient.invalidateQueries({ queryKey: ["activity-history", ctx.amoCode || "unknown", ctx.department || "quality"] });
  }, [ctx.amoCode, ctx.department, lastEventKey, queryClient]);

  const connectSse = useCallback(() => {
    controllerRef.current?.abort();
    if (isPlatformUser || isLoginSurface()) {
      setStatus("offline");
      setBrokerState("offline");
      return;
    }
    const token = getToken();
    if (!token) {
      setStatus("offline");
      return;
    }
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      setStatus("offline");
      setIsOnline(false);
      return;
    }

    const persisted = typeof window !== "undefined" ? window.localStorage.getItem(lastEventKey) : null;
    setStatus("syncing");
    const controller = new AbortController();
    controllerRef.current = controller;

    void (async () => {
      try {
        const qs = new URLSearchParams();
        if (persisted) qs.set("lastEventId", persisted);
        const url = `${getApiBaseUrl()}/api/events${qs.toString() ? `?${qs.toString()}` : ""}`;
        const res = await fetch(url, {
          method: "GET",
          signal: controller.signal,
          credentials: "include",
          headers: { Accept: "text/event-stream", Authorization: `Bearer ${token}`, "Cache-Control": "no-cache" },
        });
        if (!res.ok || !res.body) throw new RealtimeHttpError(`SSE connect failed: ${res.status}`, res.status);

        retryCount.current = 0;
        setStatus("live");
        setIsOnline(true);
        setLastUpdated(serverNow());
        setStaleSeconds(0);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let splitIndex = buffer.indexOf("\n\n");
          while (splitIndex >= 0) {
            const block = buffer.slice(0, splitIndex);
            buffer = buffer.slice(splitIndex + 2);
            const parsedBlock = parseSseBlock(block);
            if (parsedBlock?.event === "reset") {
              window.localStorage.removeItem(lastEventKey);
            } else if (parsedBlock) {
              try { handleEvent(JSON.parse(parsedBlock.data), parsedBlock.id); } catch { /* noop */ }
            }
            splitIndex = buffer.indexOf("\n\n");
          }
        }

        if (!controller.signal.aborted) {
          setStatus("offline");
          reconnectTimer.current = window.setTimeout(() => connectRef.current(), 1500);
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        setStatus("offline");
        if (err instanceof RealtimeHttpError && (err.status === 401 || err.status === 403)) {
          reconnectTimer.current = window.setTimeout(() => connectRef.current(), 30_000);
          return;
        }
        const retryDelay = Math.min(15000, 2000 * 2 ** retryCount.current);
        retryCount.current += 1;
        reconnectTimer.current = window.setTimeout(() => connectRef.current(), retryDelay);
      }
    })();
  }, [handleEvent, isPlatformUser, lastEventKey, serverNow]);

  const reconnectNow = useCallback(() => {
    retryCount.current = 0;
    controllerRef.current?.abort();
    connectRef.current();
  }, []);

  useEffect(() => {
    return onSessionEvent((detail) => {
      if (!isRealtimeEnabled()) return;
      if (detail.type === "authenticated") {
        retryCount.current = 0;

        mqttRef.current?.disconnect();
        mqttRef.current = null;
        if (isPlatformUser) {
          controllerRef.current?.abort();
          setStatus("offline");
          setBrokerState("offline");
          return;
        }
        if (!isRealtimeEnabled()) {
          controllerRef.current?.abort();
          setStatus("offline");
          setBrokerState("offline");
          return;
        }

        reconnectNow();

        mqttRef.current = new RealtimeMqttClient({
          onState: (state) => {
            setBrokerState(state);
            if (state === "connected") {
              frozenClockRef.current = null;
              void syncServerTime();
            } else if (frozenClockRef.current === null) {
              frozenClockRef.current = Date.now() + clockOffsetMsRef.current;
            }
          },
          onMessage: () => setLastUpdated(serverNow()),
          onUnavailable: () => setBrokerState("offline"),
        });
        void mqttRef.current.connect();
      }

      if (detail.type === "expired" || detail.type === "idle-logout" || detail.type === "manual-logout") {
        controllerRef.current?.abort();
        mqttRef.current?.disconnect();
        mqttRef.current = null;
        setStatus("offline");
        setBrokerState("offline");
      }
    });
  }, [isPlatformUser, reconnectNow, serverNow, syncServerTime]);

  useEffect(() => {
    connectRef.current = connectSse;

    if (getToken()) {
      if (isPlatformUser || isLoginSurface()) {
        controllerRef.current?.abort();
        setStatus("offline");
        setBrokerState("offline");
        return () => {
          controllerRef.current?.abort();
          if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
        };
      }
      if (!isRealtimeEnabled()) {
        controllerRef.current?.abort();
        setStatus("offline");
        setBrokerState("offline");
        return () => {
          controllerRef.current?.abort();
          if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
        };
      }
      connectSse();
      if (!isRealtimeEnabled()) {
        setBrokerState("offline");
        return () => {
          controllerRef.current?.abort();
          if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
        };
      }
      mqttRef.current = new RealtimeMqttClient({
        onState: (state) => {
          setBrokerState(state);
          if (state === "connected") {
            frozenClockRef.current = null;
            void syncServerTime();
          } else if (frozenClockRef.current === null) {
            frozenClockRef.current = Date.now() + clockOffsetMsRef.current;
          }
        },
        onMessage: () => setLastUpdated(serverNow()),
        onUnavailable: () => setBrokerState("offline"),
      });
      void mqttRef.current.connect();
    } else {
      setStatus("offline");
      setBrokerState("offline");
    }

    return () => {
      controllerRef.current?.abort();
      mqttRef.current?.disconnect();
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
    };
  }, [connectSse, isPlatformUser, serverNow, syncServerTime]);

  useEffect(() => {
    if (staleIntervalRef.current) window.clearInterval(staleIntervalRef.current);
    if (!isStale) {
      setStaleSeconds(0);
      return;
    }
    staleIntervalRef.current = window.setInterval(() => setStaleSeconds((prev) => prev + 1), 1000);
    return () => {
      if (staleIntervalRef.current) window.clearInterval(staleIntervalRef.current);
    };
  }, [isStale]);


  useEffect(() => {
    setCurrentTime(serverNow());
    const timer = window.setInterval(() => setCurrentTime(serverNow()), 1000);
    return () => window.clearInterval(timer);
  }, [serverNow, clockSource]);

  useEffect(() => {
    const onOnline = () => {
      setIsOnline(true);
      reconnectNow();
      void syncServerTime();
    };
    const onOffline = () => {
      setIsOnline(false);
      setStatus("offline");
      setBrokerState("offline");
      controllerRef.current?.abort();
      if (frozenClockRef.current === null) frozenClockRef.current = Date.now() + clockOffsetMsRef.current;
    };
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [reconnectNow, syncServerTime]);

  useEffect(() => {
    const refreshHealth = async () => {
      try {
        const health = await fetchHealthz();
        setBackendHealth(health.status === "ok" ? "ok" : "degraded");
      } catch {
        setBackendHealth("degraded");
      }
    };

    const hasToken = !!getToken();
    const kickoff = () => {
      if (hasToken) {
        void syncServerTime();
      }
      void refreshHealth();
    };
    const initialTimer = window.setTimeout(kickoff, hasToken ? 2500 : 1000);
    const timer = window.setInterval(() => {
      void refreshHealth();
    }, 180_000);
    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(timer);
    };
  }, [syncServerTime]);

  useEffect(() => {
    if (isPlatformUser || isLoginSurface() || !getToken() || !isRealtimeEnabled()) return;

    const pushPresence = () => {
      const state = typeof document !== "undefined" && document.hidden ? "away" : "online";
      void sendPresenceHeartbeat(state);
    };

    pushPresence();
    const timer = window.setInterval(pushPresence, 45_000);
    const handleVisibility = () => pushPresence();
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [isPlatformUser, sendPresenceHeartbeat]);

  const refreshData = useCallback(() => {
    queryClient.invalidateQueries();
    reconnectNow();
  }, [queryClient, reconnectNow]);

  const triggerSync = useCallback(() => refreshData(), [refreshData]);

  const value = useMemo(
    () => ({
      status,
      brokerState,
      backendHealth,
      lastGoodServerTime,
      lastClockSyncAt,
      lastUpdated,
      currentTime,
      activity,
      isStale,
      staleSeconds,
      isOnline,
      clockSource,
      refreshData,
      triggerSync,
    }),
    [status, brokerState, backendHealth, lastGoodServerTime, lastClockSyncAt, lastUpdated, currentTime, activity, isStale, staleSeconds, isOnline, clockSource, refreshData, triggerSync]
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
};
