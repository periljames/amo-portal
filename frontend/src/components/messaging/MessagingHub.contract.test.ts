import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const hub = readFileSync(new URL("./MessagingHub.tsx", import.meta.url), "utf8");

describe("MessagingHub notification lifecycle contract", () => {
  it("marks collapsed lifecycle notifications read before opening the latest item", () => {
    expect(hub).toContain("const markNotificationGroupSeen = async (items: PortalNotification[])");
    expect(hub).toContain("items.filter((item) => !item.read_at)");
    expect(hub).toContain("Promise.allSettled(unread.map((item) => messagingApi.markNotificationReadOnly(item.id)))");
    expect(hub).toContain("await markNotificationGroupSeen(hiddenUnread)");
    expect(hub).toContain("onRead(latest)");
  });

  it("clears the complete grouped unread state before navigating to Ask AI", () => {
    expect(hub).toContain("const askAi = async (items: PortalNotification[])");
    expect(hub).toContain("await markNotificationGroupSeen(items)");
    expect(hub).toContain("void askAi(items)");
  });
});
