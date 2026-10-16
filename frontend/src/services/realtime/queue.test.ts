import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installOfflineBrowser } from "../../test/offlineBrowser";
import { loadOutbound, MAX_OUTBOUND_MESSAGES, queueOutbound, removeOutbound } from "./queue";
import type { RealtimeEnvelope } from "./types";

const scope = { amoId: "amo", userId: "user" };
function message(id: string, userId = "user"): RealtimeEnvelope {
  return { v: 1, id, ts: 1, amoId: "amo", userId, kind: "chat.send", payload: { body: id } };
}
beforeEach(() => { installOfflineBrowser(); });
afterEach(() => { vi.unstubAllGlobals(); });

describe("message queue ownership", () => {
  it("isolates load and acknowledgement across accounts", async () => {
    await queueOutbound(message("one"));
    await queueOutbound(message("two", "other"));
    expect((await loadOutbound(scope)).map((row) => row.id)).toEqual(["one"]);
    await removeOutbound("one", { ...scope, userId: "other" });
    expect(await loadOutbound(scope)).toHaveLength(1);
    await removeOutbound("one", scope);
    expect(await loadOutbound(scope)).toHaveLength(0);
    await removeOutbound("two", { ...scope, userId: "other" });
  });
  it("preserves unsent messages when the per-account queue is full", async () => {
    await Promise.all(Array.from({ length: MAX_OUTBOUND_MESSAGES }, (_, i) => queueOutbound(message(`full-${i}`))));
    await expect(queueOutbound(message("overflow"))).rejects.toThrow(/retained/);
    const retained = await loadOutbound(scope);
    expect(retained).toHaveLength(MAX_OUTBOUND_MESSAGES);
    expect(retained.some((row) => row.id === "full-0")).toBe(true);
    await Promise.all(retained.map((row) => removeOutbound(row.id, scope)));
  });
});
