import { getToken } from "./auth";
import { getApiBaseUrl } from "./config";

export type QmsAuditRealtimeEvent = {
  id?: string;
  event: string;
  data: unknown;
};

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

function abortDelay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const timer = window.setTimeout(resolve, ms);
    signal.addEventListener("abort", () => { window.clearTimeout(timer); resolve(); }, { once: true });
  });
}

export function startQmsAuditRealtimeStream(handlers: StreamHandlers): () => void {
  const controller = new AbortController();
  let lastEventId = "";

  const run = async () => {
    let attempt = 0;
    while (!controller.signal.aborted) {
      const token = getToken();
      if (!token) {
        handlers.onState?.("offline");
        return;
      }
      try {
        handlers.onState?.(attempt ? "reconnecting" : "connected");
        const response = await fetch(`${getApiBaseUrl()}/api/events`, {
          headers: {
            Accept: "text/event-stream",
            Authorization: `Bearer ${token}`,
            ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
          },
          cache: "no-store",
          credentials: "include",
          signal: controller.signal,
        });
        if (!response.ok || !response.body) throw new Error(`QMS event stream failed with status ${response.status}.`);
        handlers.onState?.("connected");
        attempt = 0;
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
            const parsed = parseQmsSseBlock(block);
            if (parsed) {
              if (parsed.id) lastEventId = parsed.id;
              if (parsed.event !== "heartbeat") handlers.onEvent(parsed);
            }
            boundary = buffer.indexOf("\n\n");
          }
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        console.warn("[qms-realtime] audit event stream disconnected", error);
      }
      attempt += 1;
      handlers.onState?.("reconnecting");
      await abortDelay(Math.min(15_000, 750 * 2 ** Math.min(attempt, 4)), controller.signal);
    }
  };

  void run();
  return () => {
    controller.abort();
    handlers.onState?.("offline");
  };
}
