import { useCallback, useEffect, useRef, useState } from "react";

import { getToken } from "../../../services/auth";
import { readPlatformDataMode } from "../../../services/platformEnvironment";
import { operationsStreamUrl, type DataMode } from "../../../services/platformOperations";
import "../../../styles/platform-realtime-ownership.css";

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

class PlatformRealtimeRequestError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly terminal: boolean,
  ) {
    super(message);
    this.name = "PlatformRealtimeRequestError";
  }
}

export function isTerminalPlatformRealtimeStatus(status: number): boolean {
  // A 404/405 is not a transient stream interruption. It means /ops is routed
  // to the wrong process or the deployed gateway is incompatible with this UI.
  // Retrying indefinitely only floods the browser/network logs and hides the
  // deployment fault. Manual reconnect remains available after the route is fixed.
  return status === 404 || status === 405;
}

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

export function shouldUseShellOperationsStream(enabled: boolean, _pathname: string): boolean {
  return enabled;
}

/**
 * Own the single shared Platform browser SSE connection.
 *
 * PlatformShell is the sole owner of the isolated Operations Gateway stream on
 * every Platform route. Pages, including `/platform/operations`, consume the
 * normalized `amo:platform-live` browser event rather than opening a second
 * stream. This keeps one realtime connection per Superadmin Platform session.
 */
export function usePlatformRealtime(enabled = true, dataMode?: DataMode) {
  const pathname = typeof window !== "undefined" ? window.location.pathname : "";
  const streamEnabled = shouldUseShellOperationsStream(enabled, pathname);
  const selectedMode = dataMode || (typeof window !== "undefined" ? readPlatformDataMode(window.location.search) : "REAL");
  const [status, setStatus] = useState<PlatformLiveStatus>(streamEnabled ? "connecting" : "offline");
  const [snapshot, setSnapshot] = useState<PlatformConsoleSnapshot | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [lastEvent, setLastEvent] = useState<PlatformConsoleEvent | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const statusRef = useRef<PlatformLiveStatus>(streamEnabled ? "connecting" : "offline");
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
    if (!streamEnabled) return;

    const token = getToken();
    if (!token || (typeof navigator !== "undefined" && !navigator.onLine)) {
      updateStatus("offline");
      setLastError(!token ? "Platform session is unavailable." : "Browser is offline.");
      return;
    }

    const controller = new AbortController();
    controllerRef.current = controller;
    updateStatus("connecting");
    setLastError(null);

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
        if (!response.ok || !response.body) {
          const body = await response.text().catch(() => "");
          const detail = body ? `: ${body.slice(0, 180)}` : "";
          throw new PlatformRealtimeRequestError(
            response.status,
            `Platform Operations live stream failed (${response.status})${detail}`,
            isTerminalPlatformRealtimeStatus(response.status),
          );
        }

        retryRef.current = 0;
        setLastError(null);
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
      } catch (error) {
        if (controller.signal.aborted || !streamEnabled) return;
        updateStatus("offline");
        setLastError(error instanceof Error ? error.message : "Platform live stream failed.");
        if (error instanceof PlatformRealtimeRequestError && error.terminal) {
          retryRef.current = 0;
          return;
        }
        const delay = Math.min(30_000, 1_500 * 2 ** retryRef.current);
        retryRef.current += 1;
        reconnectRef.current = window.setTimeout(() => connectRef.current(), delay);
      }
    })();
  }, [publish, selectedMode, streamEnabled, updateStatus]);

  const reconnect = useCallback(() => {
    if (!streamEnabled) return;
    retryRef.current = 0;
    setLastError(null);
    connectRef.current();
  }, [streamEnabled]);

  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    const root = document.documentElement;
    const owner = enabled ? "platform-shell" : "none";
    root.dataset.platformRealtimeOwner = owner;
    return () => {
      if (root.dataset.platformRealtimeOwner === owner) delete root.dataset.platformRealtimeOwner;
    };
  }, [enabled]);

  useEffect(() => {
    connectRef.current = connect;
    if (!streamEnabled) {
      controllerRef.current?.abort();
      if (reconnectRef.current) window.clearTimeout(reconnectRef.current);
      updateStatus("offline");
      setLastError(null);
      return;
    }
    connect();
    const online = () => reconnect();
    const offline = () => {
      controllerRef.current?.abort();
      updateStatus("offline");
      setLastError("Browser is offline.");
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
  }, [connect, reconnect, streamEnabled, updateStatus]);

  return { status, snapshot, lastUpdated, lastEvent, lastError, reconnect };
}

export const PLATFORM_CONSOLE_LIVE_EVENT = PLATFORM_LIVE_EVENT;
