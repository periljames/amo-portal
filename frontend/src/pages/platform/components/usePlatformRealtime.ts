import { useCallback, useEffect, useRef, useState } from "react";

import { getToken } from "../../../services/auth";
import { readPlatformDataMode } from "../../../services/platformEnvironment";
import { operationsStreamUrl, type DataMode } from "../../../services/platformOperations";

export type PlatformLiveStatus = "connecting" | "live" | "offline";

export type PlatformConsoleSnapshot = Record<string, unknown> & {
  generated_at?: string;
  data_mode?: DataMode;
  overview?: Record<string, unknown>;
};

export type PlatformConsoleEvent = {
  id?: string;
  type: string;
  action?: string;
  entity_type?: string | null;
  entity_id?: string | null;
  tenant_id?: string | null;
  created_at?: string;
  details?: Record<string, unknown>;
  snapshot?: PlatformConsoleSnapshot;
};

type ParsedSseBlock = {
  event: string;
  id?: string;
  data: string;
};

const PLATFORM_LIVE_EVENT = "amo:platform-live";

function parseSseBlock(block: string): ParsedSseBlock | null {
  let event = "message";
  let id: string | undefined;
  const data: string[] = [];
  for (const rawLine of block.split(/\r?\n/)) {
    const line = rawLine.trimEnd();
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim() || "message";
    else if (line.startsWith("id:")) id = line.slice(3).trim() || undefined;
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  return data.length ? { event, id, data: data.join("\n") } : null;
}

function normalizedEvent(event: PlatformConsoleEvent): PlatformConsoleEvent {
  const source = event.snapshot;
  if (!source) return event;
  // Legacy Platform navigation badges read a few summary keys at the snapshot
  // root. Preserve that compatibility while the authoritative Ops payload keeps
  // those fields grouped under `overview`.
  const normalizedSnapshot: PlatformConsoleSnapshot = {
    ...(source.overview || {}),
    ...source,
  };
  return { ...event, snapshot: normalizedSnapshot };
}

/**
 * Own the single Platform browser SSE connection.
 *
 * Every Platform page is rendered inside PlatformShell, so the shell connects to
 * the isolated Operations Gateway once and republishes snapshot frames as a
 * window event for page-level consumers. Individual pages must not open their
 * own competing Platform SSE connection.
 */
export function usePlatformRealtime(enabled = true, dataMode?: DataMode) {
  const selectedMode = dataMode || (typeof window !== "undefined" ? readPlatformDataMode(window.location.search) : "REAL");
  const [status, setStatus] = useState<PlatformLiveStatus>(enabled ? "connecting" : "offline");
  const [snapshot, setSnapshot] = useState<PlatformConsoleSnapshot | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [lastEvent, setLastEvent] = useState<PlatformConsoleEvent | null>(null);
  const statusRef = useRef<PlatformLiveStatus>(enabled ? "connecting" : "offline");
  const controllerRef = useRef<AbortController | null>(null);
  const reconnectRef = useRef<number | null>(null);
  const retryRef = useRef(0);
  const connectRef = useRef<() => void>(() => undefined);

  const updateStatus = useCallback((next: PlatformLiveStatus) => {
    statusRef.current = next;
    setStatus(next);
  }, []);

  const publish = useCallback((rawEvent: PlatformConsoleEvent) => {
    const event = normalizedEvent(rawEvent);
    setLastEvent(event);
    setLastUpdated(new Date(event.created_at || event.snapshot?.generated_at || Date.now()));
    if (event.snapshot) setSnapshot(event.snapshot);
    window.dispatchEvent(new CustomEvent<PlatformConsoleEvent>(PLATFORM_LIVE_EVENT, { detail: event }));
  }, []);

  const connect = useCallback(() => {
    controllerRef.current?.abort();
    if (reconnectRef.current) window.clearTimeout(reconnectRef.current);
    if (!enabled) return;

    const token = getToken();
    if (!token || (typeof navigator !== "undefined" && !navigator.onLine)) {
      updateStatus("offline");
      return;
    }

    const controller = new AbortController();
    controllerRef.current = controller;
    updateStatus("connecting");

    void (async () => {
      try {
        const response = await fetch(operationsStreamUrl(selectedMode), {
          method: "GET",
          credentials: "include",
          signal: controller.signal,
          headers: {
            Accept: "text/event-stream",
            Authorization: `Bearer ${token}`,
            "Cache-Control": "no-cache",
          },
        });
        if (!response.ok || !response.body) throw new Error(`Platform live stream failed: ${response.status}`);

        retryRef.current = 0;
        updateStatus("live");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!controller.signal.aborted) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
          let boundary = buffer.indexOf("\n\n");
          while (boundary >= 0) {
            const block = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            const parsed = parseSseBlock(block);
            if (parsed) {
              try {
                const payload = JSON.parse(parsed.data) as PlatformConsoleEvent;
                publish({ ...payload, id: parsed.id || payload.id, type: payload.type || parsed.event });
              } catch {
                // Ignore malformed frames and keep the stream alive.
              }
            }
            boundary = buffer.indexOf("\n\n");
          }
        }
        if (!controller.signal.aborted) throw new Error("Platform live stream closed");
      } catch {
        if (controller.signal.aborted || !enabled) return;
        updateStatus("offline");
        const delay = Math.min(30_000, 1_500 * 2 ** retryRef.current);
        retryRef.current += 1;
        reconnectRef.current = window.setTimeout(() => connectRef.current(), delay);
      }
    })();
  }, [enabled, publish, selectedMode, updateStatus]);

  const reconnect = useCallback(() => {
    if (!enabled) return;
    retryRef.current = 0;
    connectRef.current();
  }, [enabled]);

  useEffect(() => {
    connectRef.current = connect;
    if (!enabled) {
      updateStatus("offline");
      return;
    }
    connect();
    const online = () => reconnect();
    const offline = () => {
      controllerRef.current?.abort();
      updateStatus("offline");
    };
    const visible = () => {
      if (document.visibilityState === "visible" && statusRef.current !== "live") reconnect();
    };
    window.addEventListener("online", online);
    window.addEventListener("offline", offline);
    document.addEventListener("visibilitychange", visible);
    return () => {
      controllerRef.current?.abort();
      if (reconnectRef.current) window.clearTimeout(reconnectRef.current);
      window.removeEventListener("online", online);
      window.removeEventListener("offline", offline);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [connect, enabled, reconnect, updateStatus]);

  return { status, snapshot, lastUpdated, lastEvent, reconnect };
}

export const PLATFORM_CONSOLE_LIVE_EVENT = PLATFORM_LIVE_EVENT;
