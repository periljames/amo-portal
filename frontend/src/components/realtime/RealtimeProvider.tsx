import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { getApiBaseUrl } from "../../services/config";
import { getToken } from "../../services/auth";

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

const MAX_ACTIVITY = 40;
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
  "qms-dashboard",
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
    ];
  }
  if (type.startsWith("training.") || type.startsWith("training_")) {
    return ["training-assignments", "training-dashboard", "training-events", "training-status"];
  }
  if (type.startsWith("tasks.task.")) {
    return ["tasks", "my-tasks", "qms-dashboard", "dashboard"];
  }
  if (type.startsWith("tasks.") || type.startsWith("tasks_")) {
    return ["tasks", "my-tasks"];
  }
  if (type.startsWith("accounts.") || type.startsWith("accounts_")) {
    return ["admin-users", "user-profile", "qms-dashboard", "dashboard"];
  }
  return ["dashboard"]; 
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
      setStatus("live");
      setLastUpdated(new Date(event.timestamp));
      setStaleSeconds(0);
      setActivity((prev) => {
        const next = [event, ...prev];
        return next.slice(0, MAX_ACTIVITY);
      });
      scheduleInvalidations(mapEventToInvalidations(event.type));
    },
    [scheduleInvalidations]
  );

  const connect = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close();
    }
    setStatus("syncing");
    const token = getToken();
    const qs = token ? `?token=${encodeURIComponent(token)}` : "";
    const url = `${getApiBaseUrl()}/api/events${qs}`;
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
  }, [handleEvent]);

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
