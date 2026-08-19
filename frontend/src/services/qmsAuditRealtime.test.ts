import { describe, expect, it } from "vitest";

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
});
