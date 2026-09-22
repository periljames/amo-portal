import { describe, expect, it, vi } from "vitest";

import { parseQmsSseBlock } from "./qmsAuditRealtime";

describe("QMS audit realtime SSE parser", () => {
  it("parses event id, custom event type and JSON payload", () => {
    const parsed = parseQmsSseBlock([
      "id: event-42",
      "event: qms.audit.checklist_item.updated",
      "data: {\"type\":\"qms.audit.checklist_item.updated\",\"metadata\":{\"auditId\":\"audit-1\"}}",
    ].join("\n"));
    expect(parsed).toEqual({
      id: "event-42",
      event: "qms.audit.checklist_item.updated",
      data: { type: "qms.audit.checklist_item.updated", metadata: { auditId: "audit-1" } },
    });
  });

  it("preserves reset packets so the caller can force a complete active-query refresh", () => {
    const parsed = parseQmsSseBlock("event: reset\ndata: {\"type\":\"reset\",\"reason\":\"last_event_id_out_of_window\"}");
    expect(parsed?.event).toBe("reset");
    expect(parsed?.data).toEqual({ type: "reset", reason: "last_event_id_out_of_window" });
  });

  it("joins multiline data and ignores comments", () => {
    const parsed = parseQmsSseBlock(": keepalive\nevent: activity\ndata: first\ndata: second");
    expect(parsed).toEqual({ event: "activity", data: "first\nsecond" });
  });

  it("bridges shell realtime instead of opening a dedicated /api/events fetch", async () => {
    const listeners = new Map<string, Set<EventListener>>();
    vi.stubGlobal("window", {
      addEventListener: (type: string, listener: EventListener) => {
        const set = listeners.get(type) ?? new Set();
        set.add(listener);
        listeners.set(type, set);
      },
      removeEventListener: (type: string, listener: EventListener) => {
        listeners.get(type)?.delete(listener);
      },
      dispatchEvent: (event: Event) => {
        for (const listener of listeners.get(event.type) ?? []) listener(event);
        return true;
      },
    });
    vi.stubGlobal("CustomEvent", class CustomEvent<T> extends Event {
      detail: T;
      constructor(type: string, init?: CustomEventInit<T>) {
        super(type);
        this.detail = init?.detail as T;
      }
    });

    try {
      const { startQmsAuditRealtimeStream, publishQmsRealtimeEvent } = await import("./qmsAuditRealtime");
      const seen: string[] = [];
      const stop = startQmsAuditRealtimeStream({
        onEvent: (event) => { seen.push(event.event); },
      });
      publishQmsRealtimeEvent({
        event: "qms.audit.updated",
        data: { type: "qms.audit.updated", metadata: { auditId: "a1", module: "quality" } },
      });
      expect(seen).toEqual(["qms.audit.updated"]);
      stop();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
