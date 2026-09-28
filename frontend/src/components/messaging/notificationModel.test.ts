import { describe, expect, it } from "vitest";

import type { PortalNotification } from "../../services/messaging";
import {
  canAskAi,
  notificationActionLabel,
  notificationDueAt,
  notificationGroupKey,
  notificationModule,
  notificationPriority,
  notificationRequiresAction,
} from "./notificationModel";

function notification(overrides: Partial<PortalNotification> = {}): PortalNotification {
  return {
    id: "n-1",
    kind: "DOCUMENT_CONTROL",
    title: "Document acknowledgement due",
    body: "Review and acknowledge the controlled publication.",
    entity_type: "document_distribution_campaign",
    entity_id: "campaign-1",
    action_url: "/maintenance/tenant/document-control/library/manual-1",
    metadata: {},
    created_at: "2026-09-28T10:00:00Z",
    ...overrides,
  };
}

describe("notification presentation model", () => {
  it("treats explicit requires_action false as authoritative", () => {
    expect(notificationRequiresAction(notification({ metadata: { requires_action: false } }))).toBe(false);
  });

  it("uses governed semantic metadata when supplied", () => {
    const row = notification({
      metadata: {
        module: "DMS",
        priority: "HIGH",
        requires_action: true,
        action_label: "Review & acknowledge",
        group_key: "document-publication:manual-1:rev-1",
        due_at: "2026-10-05T06:44:34Z",
      },
    });
    expect(notificationModule(row)).toBe("DMS");
    expect(notificationPriority(row)).toBe("HIGH");
    expect(notificationActionLabel(row)).toBe("Review & acknowledge");
    expect(notificationGroupKey(row)).toBe("document-publication:manual-1:rev-1");
    expect(notificationDueAt(row)?.toISOString()).toBe("2026-10-05T06:44:34.000Z");
  });

  it("only offers AI linking for controlled document context with an action target", () => {
    expect(canAskAi(notification({ metadata: { manual_id: "manual-1" } }))).toBe(true);
    expect(canAskAi(notification({ action_url: null, metadata: { manual_id: "manual-1" } }))).toBe(false);
    expect(canAskAi(notification({ entity_type: "training_event", metadata: {} }))).toBe(false);
  });
});
