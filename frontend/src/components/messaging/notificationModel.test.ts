import { describe, expect, it } from "vitest";

import type { PortalNotification } from "../../services/messaging";
import {
  groupNotifications,
  notificationMatches,
  notificationNeedsAttention,
  notificationTone,
} from "./notificationModel";

function row(overrides: Partial<PortalNotification> = {}): PortalNotification {
  return {
    id: overrides.id || crypto.randomUUID(),
    kind: "DOCUMENT_CONTROL",
    title: "Document update",
    body: "Body",
    metadata: {},
    created_at: overrides.created_at || "2026-09-28T07:00:00Z",
    ...overrides,
  };
}

describe("notification presentation model", () => {
  it("keeps read state separate from business action state", () => {
    const item = row({
      read_at: "2026-09-28T07:05:00Z",
      requires_action: true,
      business_state: "ACTION_REQUIRED",
    });
    expect(notificationNeedsAttention(item)).toBe(true);
    expect(notificationMatches(item, "for-you", "all")).toBe(true);
    expect(notificationMatches(item, "for-you", "unread")).toBe(false);
  });

  it("groups lifecycle notifications without deleting history", () => {
    const grouped = groupNotifications([
      row({ id: "1", group_key: "doc:abc", created_at: "2026-09-28T06:00:00Z" }),
      row({ id: "2", group_key: "doc:abc", created_at: "2026-09-28T07:00:00Z" }),
      row({ id: "3", group_key: "doc:def", created_at: "2026-09-28T05:00:00Z" }),
    ]);
    expect(grouped).toHaveLength(2);
    expect(grouped[0].latest.id).toBe("2");
    expect(grouped[0].earlier.map((item) => item.id)).toEqual(["1"]);
  });

  it("uses critical treatment for overdue obligations", () => {
    const item = row({ business_state: "OVERDUE", priority: "CRITICAL", requires_action: true });
    expect(notificationTone(item)).toBe("critical");
  });
});
