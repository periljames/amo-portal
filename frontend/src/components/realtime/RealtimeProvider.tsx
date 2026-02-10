import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { getApiBaseUrl } from "../../services/config";
import { getContext, getToken } from "../../services/auth";

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

const TARGETED_REFRESH_KEYS = [
  "dashboard",
  "qms-dashboard",
  "qms-documents",
  "qms-audits",
  "qms-cars",
  "qms-change-requests",
  "qms-distributions",
  "training-assignments",
  "training-dashboard",
  "training-events",
  "training-status",
  "tasks",
  "my-tasks",
  "admin-users",
  "user-profile",
  "activity-history",
] as const;

function mapEventToInvalidations(type: string): string[] {
  if (type.startsWith("qms.") || type.startsWith("qms_")) {
    return [
      "qms-dashboard",
      "qms-documents",
      "qms-audits",
      "qms-cars",
      "qms-change-requests",
      "qms-distributions",
      "activity-history",
    ];
  }
  if (type.startsWith("training.") || type.startsWith("training_")) {
    return ["training-assignments", "training-dashboard", "training-events", "training-status", "activity-history"];
  }
  if (type.startsWith("tasks.task.")) {
    return ["tasks", "my-tasks", "qms-dashboard", "dashboard", "activity-history"];
  }
  if (type.startsWith("tasks.") || type.startsWith("tasks_")) {
    return ["tasks", "my-tasks", "activity-history"];
  }
  if (type.startsWith("accounts.") || type.startsWith("accounts_")) {
    return ["admin-users", "user-profile", "qms-dashboard", "dashboard", "activity-history"];
  }
  return ["dashboard", "activity-history"];
}

export const RealtimeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<RealtimeStatus>("syncing");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const sourceRef = useRef<EventSource | null>(null);
  const invalidateTimer = useRef<number | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const retryCount = useRef(0);
  const staleIntervalRef = useRef<number | null>(null);
  const [staleSeconds, setStaleSeconds] = useState(0);
  const ctx = getContext();
  const lastEventKey = `amo:last-event-id:${ctx.amoCode || "unknown"}`;

  const isStale = status !== "live" || staleSeconds > STALE_AFTER_SECONDS;

  const scheduleInvalidations = useCallback(
    (keys: string[]) => {
      if (invalidateTimer.current) {
        window.clearTimeout(invalidateTimer.current);
      }
      invalidateTimer.current = window.setTimeout(() => {
        keys.forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
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
      scheduleInvalidations(mapEventToInvalidations(event.type));
    },
    [lastEventKey, scheduleInvalidations]
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
      scheduleInvalidations(["activity-history", "dashboard", "qms-dashboard"]);
    });

    source.onerror = () => {
      setStatus("offline");
      source.close();
      if (reconnectTimer.current) {
        window.clearTimeout(reconnectTimer.current);
      }
      const retryDelay = Math.min(15000, 2000 * 2 ** retryCount.current);
      retryCount.current += 1;
      reconnectTimer.current = window.setTimeout(() => connect(), retryDelay);
    };
  }, [handleEvent, lastEventKey, scheduleInvalidations]);

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
    TARGETED_REFRESH_KEYS.forEach((key) => {
      queryClient.invalidateQueries({ queryKey: [key] });
    });
  }, [queryClient]);

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
