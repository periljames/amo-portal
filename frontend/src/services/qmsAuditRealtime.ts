export type QmsAuditRealtimeEvent = {
  id?: string;
  event: string;
  data: unknown;
};

export const QMS_REALTIME_EVENT = "amo:qms:realtime";
export const QMS_REALTIME_STATE_EVENT = "amo:qms:realtime-state";

export function parseQmsSseBlock(block: string): QmsAuditRealtimeEvent | null {
  let event = "message";
  let id: string | undefined;
  const data: string[] = [];
  for (const rawLine of block.split(/\r?\n/)) {
    if (!rawLine || rawLine.startsWith(":")) continue;
    const separator = rawLine.indexOf(":");
    const field = separator >= 0 ? rawLine.slice(0, separator) : rawLine;
    const value = separator >= 0 ? rawLine.slice(separator + 1).replace(/^ /, "") : "";
    if (field === "event") event = value || "message";
    else if (field === "id") id = value || undefined;
    else if (field === "data") data.push(value);
  }
  if (!data.length) return null;
  const raw = data.join("\n");
  let payload: unknown = raw;
  try { payload = JSON.parse(raw); } catch { /* textual SSE is still valid */ }
  return { id, event, data: payload };
}

type StreamHandlers = {
  onEvent: (event: QmsAuditRealtimeEvent) => void;
  onState?: (state: "connected" | "reconnecting" | "offline") => void;
};

/**
 * Subscribe to Quality realtime via the shell RealtimeProvider bridge.
 * Does not open a second `/api/events` SSE — that previously doubled the
 * long-held DB session cost per audit tab.
 */
export function startQmsAuditRealtimeStream(handlers: StreamHandlers): () => void {
  handlers.onState?.("connected");
  const onBridge = (raw: Event) => {
    const detail = (raw as CustomEvent<QmsAuditRealtimeEvent>).detail;
    if (!detail || typeof detail !== "object") return;
    if (detail.event === "heartbeat") return;
    handlers.onEvent(detail);
  };
  const onState = (raw: Event) => {
    const state = (raw as CustomEvent<"connected" | "reconnecting" | "offline">).detail;
    if (state === "connected" || state === "reconnecting" || state === "offline") {
      handlers.onState?.(state);
    }
  };
  window.addEventListener(QMS_REALTIME_EVENT, onBridge as EventListener);
  window.addEventListener(QMS_REALTIME_STATE_EVENT, onState as EventListener);
  return () => {
    window.removeEventListener(QMS_REALTIME_EVENT, onBridge as EventListener);
    window.removeEventListener(QMS_REALTIME_STATE_EVENT, onState as EventListener);
    handlers.onState?.("offline");
  };
}

export function publishQmsRealtimeEvent(event: QmsAuditRealtimeEvent): void {
  window.dispatchEvent(new CustomEvent(QMS_REALTIME_EVENT, { detail: event }));
}

export function publishQmsRealtimeState(state: "connected" | "reconnecting" | "offline"): void {
  window.dispatchEvent(new CustomEvent(QMS_REALTIME_STATE_EVENT, { detail: state }));
}
