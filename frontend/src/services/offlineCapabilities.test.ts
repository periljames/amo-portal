import { describe, expect, it } from "vitest";

import { assertOfflineReplayAllowed, classifyOfflineMutation, offlineCommandRouteKey } from "./offlineCapabilities";

describe("offline controlled-write policy", () => {
  it("allows only guarded draft operations", () => {
    expect(() => assertOfflineReplayAllowed(
      "/rostering/versions/ID-VERSION/assignments",
      "POST",
      JSON.stringify({ source_reference_id: "offline-source-1" }),
    )).not.toThrow();
    expect(() => assertOfflineReplayAllowed(
      "/rostering/assignments/ID-ASSIGNMENT",
      "PATCH",
      JSON.stringify({ expected_state_revision: 4 }),
    )).not.toThrow();
    expect(() => assertOfflineReplayAllowed(
      "/workforce/attendance-events",
      "POST",
      JSON.stringify({ idempotency_key: "attendance-device-1" }),
    )).not.toThrow();
  });

  it("rejects unguarded, destructive and authoritative operations", () => {
    expect(() => assertOfflineReplayAllowed(
      "/rostering/versions/ID-VERSION/assignments",
      "POST",
      JSON.stringify({}),
    )).toThrow(/missing its idempotency or revision guard/i);
    expect(() => assertOfflineReplayAllowed(
      "/rostering/assignments/ID-ASSIGNMENT",
      "DELETE",
    )).toThrow(/requires a live server/i);
    expect(() => assertOfflineReplayAllowed(
      "/rostering/versions/ID-VERSION/publish",
      "POST",
      JSON.stringify({}),
    )).toThrow(/requires a live server/i);
    expect(() => assertOfflineReplayAllowed(
      "/workforce/payroll/post",
      "POST",
      JSON.stringify({}),
    )).toThrow(/requires a live server/i);
  });

  it("classifies every mutation and exposes durable command route keys", () => {
    expect(classifyOfflineMutation("/unknown/new-endpoint", "POST").capability).toBe("unsupported");
    expect(classifyOfflineMutation("/anything/42", "DELETE").capability).toBe("live-only");
    expect(offlineCommandRouteKey("/rostering/versions/ID-V/assignments", "POST"))
      .toBe("rostering.version.assignment.create:ID-V");
  });
});
