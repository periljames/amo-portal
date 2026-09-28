import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const hub = readFileSync(new URL("./MessagingHub.tsx", import.meta.url), "utf8");

describe("MessagingHub notification lifecycle contract", () => {
  it("marks collapsed earlier lifecycle notifications read before opening the latest item", () => {
    expect(hub).toContain("const hiddenUnread = items.slice(1).filter((item) => !item.read_at)");
    expect(hub).toContain("Promise.allSettled(hiddenUnread.map((item) => messagingApi.markNotificationReadOnly(item.id)))");
    expect(hub).toContain("onRead(latest)");
  });
});
