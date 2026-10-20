import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const hub = readFileSync(new URL("./MessagingHub.tsx", import.meta.url), "utf8");

describe("MessagingHub notification lifecycle contract", () => {
  it("requires every grouped acknowledgement before following the authoritative workflow", () => {
    expect(hub).toContain("const markNotificationGroupSeen = async (group: NotificationGroup)");
    expect(hub).toContain("items.filter((item) => !item.read_at)");
    expect(hub).toContain("await Promise.all(unread.map((item) => messagingApi.markNotificationRead(item.id)))");
    expect(hub).toContain("const updated = await markNotificationGroupSeen(group)");
    expect(hub).toContain("if (target && updated.entity_type !== \"chat_thread\") navigate(target)");
    expect(hub).not.toContain("Promise.allSettled(earlierUnread");
  });
  it("acknowledges the entire group before asking the controlled-document assistant", () => {
    expect(hub).toContain("const askAi = async (group: NotificationGroup)");
    expect(hub).toContain("await markNotificationGroupSeen(group)");
    expect(hub).toContain("const result = await assistDocumentation(tenant");
    expect(hub).toContain("onClick={() => void askAi(group)}");
  });
});
