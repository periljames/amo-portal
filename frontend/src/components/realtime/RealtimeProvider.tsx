import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { getApiBaseUrl } from "../../services/config";
import { getContext, getToken } from "../../services/auth";
import { playNotificationChirp, pushDesktopNotification } from "../../services/notificationPreferences";

export type RealtimeStatus = "live" | "syncing" | "offline";

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

type RealtimeContextValue = {
  status: RealtimeStatus;
  lastUpdated: Date | null;
  activity: ActivityEvent[];
  isStale: boolean;
  staleSeconds: number;
  isOnline: boolean;
  clockSource: "server" | "local";
  refreshData: () => void;
  triggerSync: () => void;
};

const RealtimeContext = createContext<RealtimeContextValue | null>(null);

const eventSchema = z.object({
  id: z.string(),
  type: z.string(),
  entityType: z.string(),
  entityId: z.string(),
  action: z.string(),
  timestamp: z.string(),
  actor: z
    .object({
      userId: z.string().optional(),
      name: z.string().optional(),
      department: z.string().optional(),
    })
    .nullable()
    .optional(),
  metadata: z.record(z.unknown()).optional(),
});

const MAX_ACTIVITY = 1500;
const HEARTBEAT_MS = 30_000;

type ParsedSseEvent = { event: string; data: string; id?: string };

function parseSseBlock(block: string): ParsedSseEvent | null {
  const lines = block.split(/\r?\n/);
  let event = "message";
  let id: string | undefined;
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      event = line.slice(6).trim() || "message";
      continue;
    }
    if (line.startsWith("id:")) {
      id = line.slice(3).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (!dataLines.length) return null;
  return { event, data: dataLines.join("\n"), id };
}

function eventAmoCode(event: ActivityEvent, fallbackAmo: string): string {
  const meta = event.metadata as Record<string, unknown> | undefined;
  const fromMeta = meta?.amoCode ?? meta?.amo_code ?? meta?.amoId;
  return typeof fromMeta === "string" && fromMeta.trim() ? fromMeta : fallbackAmo;
}

function mapEventToInvalidations(event: ActivityEvent, amoCode: string, department: string): Array<readonly [string, ...string[]]> {
  const envelope = `${event.entityType}.${event.action}`.toLowerCase();
  const scopedAmo = eventAmoCode(event, amoCode);
  const baseKeys: Array<readonly [string, ...string[]]> = [["activity-history", scopedAmo, department]];

  if (envelope.startsWith("accounts.user")) {
    return [...baseKeys, ["user-profile"], ["admin-users"], ["qms-dashboard", scopedAmo, "quality"], ["dashboard", scopedAmo, "quality"]];
  }
  if (envelope.startsWith("tasks.task")) {
    return [...baseKeys, ["tasks"], ["my-tasks"], ["qms-dashboard", scopedAmo, "quality"], ["dashboard", scopedAmo, "quality"]];
  }
  if (envelope.startsWith("qms.document")) {
    return [...baseKeys, ["qms-documents"], ["qms-dashboard", scopedAmo, "quality"]];
  }
  if (envelope.startsWith("qms.audit")) {
    return [...baseKeys, ["qms-audits"], ["qms-dashboard", scopedAmo, "quality"]];
  }
  if (envelope.startsWith("qms.car")) {
    return [...baseKeys, ["qms-cars"], ["qms-dashboard", scopedAmo, "quality"]];
  }
  if (envelope.startsWith("qms.training") || event.type.startsWith("training.")) {
    return [...baseKeys, ["training-dashboard"], ["training-events"], ["training-status"], ["qms-dashboard", scopedAmo, "quality"]];
  }
  return baseKeys;
}

export const RealtimeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<RealtimeStatus>("syncing");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const controllerRef = useRef<AbortController | null>(null);
  const invalidateTimer = useRef<number | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const connectRef = useRef<() => void>(() => undefined);
  const retryCount = useRef(0);
  const staleIntervalRef = useRef<number | null>(null);
  const [staleSeconds, setStaleSeconds] = useState(0);
  const [isOnline, setIsOnline] = useState<boolean>(typeof navigator === "undefined" ? true : navigator.onLine);
  const [clockSource, setClockSource] = useState<"server" | "local">("local");
  const clockOffsetMsRef = useRef(0);
  const heartbeatTimerRef = useRef<number | null>(null);
  const ctx = getContext();
  const lastEventKey = `amo:last-event-id:${ctx.amoCode || "unknown"}`;

  const isStale = status !== "live";

  const serverNow = useCallback(() => new Date(Date.now() + clockOffsetMsRef.current), []);

  const syncClockFromResponse = useCallback((response: Response) => {
    const serverDate = response.headers.get("date");
    if (!serverDate) return;
    const parsed = Date.parse(serverDate);
    if (Number.isNaN(parsed)) return;
    clockOffsetMsRef.current = parsed - Date.now();
    setClockSource("server");
  }, []);

  const scheduleInvalidations = useCallback(
    (keys: Array<readonly [string, ...string[]]>) => {
      if (invalidateTimer.current) {
        window.clearTimeout(invalidateTimer.current);
      }
      invalidateTimer.current = window.setTimeout(() => {
        keys.forEach((key) => queryClient.invalidateQueries({ queryKey: [...key] }));
      }, 350);
    },
    [queryClient]
  );

  const handleEvent = useCallback(
    (raw: unknown, transportCursor?: string) => {
      const parsed = eventSchema.safeParse(raw);
      if (!parsed.success) return;

      const event = parsed.data;
      const cursor = transportCursor?.trim() || event.id?.trim();
      if (!cursor) return;

      window.localStorage.setItem(lastEventKey, cursor);
      setStatus("live");
      const parsedTs = Date.parse(event.timestamp);
      setLastUpdated(Number.isNaN(parsedTs) ? serverNow() : new Date(parsedTs + clockOffsetMsRef.current));
      setStaleSeconds(0);
      setActivity((prev) => [event, ...prev].slice(0, MAX_ACTIVITY));
      playNotificationChirp();
      void pushDesktopNotification("Realtime event", `${event.type} ${event.action}`);
      scheduleInvalidations(mapEventToInvalidations(event, ctx.amoCode || "unknown", ctx.department || "quality"));
    },
    [ctx.amoCode, ctx.department, lastEventKey, scheduleInvalidations, serverNow]
  );

  const connect = useCallback(() => {
    controllerRef.current?.abort();

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

    const run = async () => {
      try {
        const qs = new URLSearchParams();
        if (persisted) qs.set("lastEventId", persisted);
        const url = `${getApiBaseUrl()}/api/events${qs.toString() ? `?${qs.toString()}` : ""}`;
        const res = await fetch(url, {
          method: "GET",
          signal: controller.signal,
          credentials: "include",
          headers: {
            Accept: "text/event-stream",
            Authorization: `Bearer ${token}`,
            "Cache-Control": "no-cache",
          },
        });

        syncClockFromResponse(res);

        if (!res.ok || !res.body) {
          setStatus("offline");
          throw new Error(`SSE connect failed: ${res.status}`);
        }

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
            if (parsedBlock) {
              if (parsedBlock.event === "reset") {
                window.localStorage.removeItem(lastEventKey);
                const amo = ctx.amoCode || "unknown";
                const dept = ctx.department || "quality";
                scheduleInvalidations([
                  ["activity-history", amo, dept],
                  ["dashboard", amo, dept],
                  ["qms-dashboard", amo, "quality"],
                ]);
                controller.abort();
                setStatus("syncing");
                if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
                reconnectTimer.current = window.setTimeout(() => connectRef.current(), 250);
                return;
              }
              try {
                const payload = JSON.parse(parsedBlock.data);
                handleEvent(payload, parsedBlock.id);
              } catch {
                // ignore malformed events
              }
            }
            splitIndex = buffer.indexOf("\n\n");
          }
        }

        if (!controller.signal.aborted) {
          setStatus("offline");
          if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
          reconnectTimer.current = window.setTimeout(() => connectRef.current(), 1500);
        }
      } catch {
        if (controller.signal.aborted) return;
        if (typeof navigator !== "undefined") setIsOnline(navigator.onLine);
        setStatus("offline");
        if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
        const retryDelay = Math.min(15000, 2000 * 2 ** retryCount.current);
        retryCount.current += 1;
        reconnectTimer.current = window.setTimeout(() => connectRef.current(), retryDelay);
      }
    };

    void run();
  }, [ctx.amoCode, ctx.department, handleEvent, lastEventKey, scheduleInvalidations, serverNow, syncClockFromResponse]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  const reconnectNow = useCallback(() => {
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      setIsOnline(false);
      setStatus("offline");
      return;
    }
    if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
    retryCount.current = 0;
    controllerRef.current?.abort();
    connectRef.current();
  }, []);

  useEffect(() => {
    connect();
    return () => {
      controllerRef.current?.abort();
      if (invalidateTimer.current) window.clearTimeout(invalidateTimer.current);
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
    };
  }, [connect]);

  useEffect(() => {
    if (staleIntervalRef.current) {
      window.clearInterval(staleIntervalRef.current);
      staleIntervalRef.current = null;
    }
    if (status === "live") {
      setStaleSeconds(0);
      return;
    }
    staleIntervalRef.current = window.setInterval(() => setStaleSeconds((prev) => prev + 1), 1000);
    return () => {
      if (staleIntervalRef.current) {
        window.clearInterval(staleIntervalRef.current);
        staleIntervalRef.current = null;
      }
    };
  }, [status]);

  useEffect(() => {
    const onOnline = () => {
      setIsOnline(true);
      reconnectNow();
    };
    const onOffline = () => {
      setIsOnline(false);
      setStatus("offline");
      controllerRef.current?.abort();
    };
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [reconnectNow]);

  useEffect(() => {
    if (heartbeatTimerRef.current) {
      window.clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }

    const token = getToken();
    if (!token) return;

    const heartbeat = async () => {
      try {
        const res = await fetch(`${getApiBaseUrl()}/api/events/history?limit=1`, {
          method: "GET",
          credentials: "include",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        syncClockFromResponse(res);
        if (res.status === 304 || res.status === 200 || res.status === 401 || res.status === 403) {
          setIsOnline(true);
          return;
        }
        if (res.status >= 500) {
          setStatus((prev) => (prev === "live" ? prev : "syncing"));
        }
      } catch {
        setIsOnline(false);
      }
    };

    void heartbeat();
    heartbeatTimerRef.current = window.setInterval(() => void heartbeat(), HEARTBEAT_MS);

    return () => {
      if (heartbeatTimerRef.current) {
        window.clearInterval(heartbeatTimerRef.current);
        heartbeatTimerRef.current = null;
      }
    };
  }, [syncClockFromResponse]);

  const refreshData = useCallback(() => {
    if (isOnline) setStatus("syncing");
    const amo = ctx.amoCode || "unknown";
    const dept = ctx.department || "quality";
    const refreshKeys: Array<readonly [string, ...string[]]> = [
      ["qms-dashboard", amo, "quality"],
      ["dashboard", amo, dept],
      ["activity-history", amo, dept],
      ["qms-audits"],
      ["qms-cars"],
      ["qms-documents"],
      ["my-tasks"],
      ["tasks"],
    ];
    refreshKeys.forEach((key) => queryClient.invalidateQueries({ queryKey: [...key] }));
    reconnectNow();
  }, [ctx.amoCode, ctx.department, isOnline, queryClient, reconnectNow]);

  const triggerSync = useCallback(() => {
    refreshData();
  }, [refreshData]);

  const value = useMemo(
    () => ({ status, lastUpdated, activity, isStale, staleSeconds, isOnline, clockSource, refreshData, triggerSync }),
    [status, lastUpdated, activity, isStale, staleSeconds, isOnline, clockSource, refreshData, triggerSync]
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
};

export function useRealtime() {
  const ctx = useContext(RealtimeContext);
  if (!ctx) {
    throw new Error("useRealtime must be used within RealtimeProvider");
  }
  return ctx;
}
