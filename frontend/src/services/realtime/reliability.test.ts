import { describe, expect, it, vi } from "vitest";

import { publishWithAcknowledgement } from "./mqtt";
import { sanitizeOutbound } from "./queue";
import type { RealtimeEnvelope } from "./types";

function clientWithCallback(callback: (cb: (error?: Error) => void) => void) {
  return {
    connected: true,
    on: vi.fn(),
    subscribe: vi.fn(),
    publish: vi.fn((_topic, _payload, _opts, cb?: (error?: Error) => void) => {
      if (cb) callback(cb);
    }),
    end: vi.fn(),
  } as Parameters<typeof publishWithAcknowledgement>[0];
}

describe("realtime publish reliability", () => {
  it("resolves only after the MQTT acknowledgement callback succeeds", async () => {
    const client = clientWithCallback((cb) => cb());
    await expect(
      publishWithAcknowledgement(client, "amo/a/user/u/outbox", new Uint8Array([1]), 1000),
    ).resolves.toBeUndefined();
  });

  it("rejects when MQTT reports a publish error", async () => {
    const client = clientWithCallback((cb) => cb(new Error("broker unavailable")));
    await expect(
      publishWithAcknowledgement(client, "amo/a/user/u/outbox", new Uint8Array([1]), 1000),
    ).rejects.toThrow("broker unavailable");
  });

  it("rejects when the broker never acknowledges the publish", async () => {
    vi.useFakeTimers();
    try {
      const client = clientWithCallback(() => undefined);
      const pending = publishWithAcknowledgement(
        client,
        "amo/a/user/u/outbox",
        new Uint8Array([1]),
        1000,
      );
      const rejection = expect(pending).rejects.toThrow("acknowledgement timed out");
      await vi.advanceTimersByTimeAsync(1000);
      await rejection;
    } finally {
      vi.useRealTimers();
    }
  });

  it("removes connect tokens before an envelope can enter IndexedDB", () => {
    const envelope: RealtimeEnvelope = {
      v: 1,
      id: "message-1",
      ts: 1,
      amoId: "amo-1",
      userId: "user-1",
      kind: "chat.send",
      payload: { body: "hello" },
      authToken: "short-lived-secret-token",
    };

    const clean = sanitizeOutbound(envelope);
    expect(clean.authToken).toBeUndefined();
    expect(envelope.authToken).toBe("short-lived-secret-token");
  });
});
