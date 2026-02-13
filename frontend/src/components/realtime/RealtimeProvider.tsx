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
const STALE_AFTER_SECONDS = 45;

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
  const sourceRef = useRef<EventSource | null>(null);
  const invalidateTimer = useRef<number | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const connectRef = useRef<() => void>(() => undefined);
  const retryCount = useRef(0);
  const staleIntervalRef = useRef<number | null>(null);
  const [staleSeconds, setStaleSeconds] = useState(0);
  const ctx = getContext();
  const lastEventKey = `amo:last-event-id:${ctx.amoCode || "unknown"}`;

  const isStale = status !== "live" || staleSeconds > STALE_AFTER_SECONDS;

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
    (raw: unknown) => {
      const parsed = eventSchema.safeParse(raw);
      if (!parsed.success) return;

      const event = parsed.data;
      window.localStorage.setItem(lastEventKey, event.id);
      setStatus("live");
      setLastUpdated(new Date(event.timestamp));
      setStaleSeconds(0);
      setActivity((prev) => {
        const next = [event, ...prev];
        return next.slice(0, MAX_ACTIVITY);
      });
      playNotificationChirp();
      void pushDesktopNotification("Realtime event", `${event.type} ${event.action}`);
      scheduleInvalidations(mapEventToInvalidations(event, ctx.amoCode || "unknown", ctx.department || "quality"));
    },
    [ctx.amoCode, ctx.department, lastEventKey, scheduleInvalidations]
  );

  const connect = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close();
    }
    setStatus("syncing");
    const token = getToken();
    const persisted = typeof window !== "undefined" ? window.localStorage.getItem(lastEventKey) : null;
    const qs = new URLSearchParams();
    if (token) qs.set("token", token);
    if (persisted) qs.set("lastEventId", persisted);
    const url = `${getApiBaseUrl()}/api/events?${qs.toString()}`;
    const source = new EventSource(url, { withCredentials: true });
    sourceRef.current = source;

    source.onopen = () => {
      retryCount.current = 0;
      setStatus("live");
      setStaleSeconds(0);
    };

    source.onmessage = (evt) => {
      try {
        const payload = JSON.parse(evt.data);
        handleEvent(payload);
      } catch {
        // ignore malformed payloads
      }
    };

    source.addEventListener("reset", () => {
      window.localStorage.removeItem(lastEventKey);
      const amo = ctx.amoCode || "unknown";
      const dept = ctx.department || "quality";
      scheduleInvalidations([
        ["activity-history", amo, dept],
        ["dashboard", amo, dept],
        ["qms-dashboard", amo, "quality"],
      ]);
    });

    source.onerror = () => {
      setStatus("offline");
      source.close();
      if (reconnectTimer.current) {
        window.clearTimeout(reconnectTimer.current);
      }
      const retryDelay = Math.min(15000, 2000 * 2 ** retryCount.current);
      retryCount.current += 1;
      reconnectTimer.current = window.setTimeout(() => connectRef.current(), retryDelay);
    };
  }, [handleEvent, lastEventKey, scheduleInvalidations]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    connect();
    staleIntervalRef.current = window.setInterval(() => {
      setStaleSeconds((prev) => prev + 1);
    }, 1000);
    return () => {
      sourceRef.current?.close();
      if (invalidateTimer.current) {
        window.clearTimeout(invalidateTimer.current);
      }
      if (reconnectTimer.current) {
        window.clearTimeout(reconnectTimer.current);
      }
      if (staleIntervalRef.current) {
        window.clearInterval(staleIntervalRef.current);
      }
    };
  }, [connect]);

  const refreshData = useCallback(() => {
    setStatus("syncing");
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
  }, [ctx.amoCode, ctx.department, queryClient]);

  const triggerSync = useCallback(() => {
    refreshData();
  }, [refreshData]);

  const value = useMemo(
    () => ({ status, lastUpdated, activity, isStale, staleSeconds, refreshData, triggerSync }),
    [status, lastUpdated, activity, isStale, staleSeconds, refreshData, triggerSync]
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
