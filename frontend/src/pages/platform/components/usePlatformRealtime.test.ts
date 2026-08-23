import { describe, expect, it } from "vitest";

import { isTerminalPlatformRealtimeStatus, shouldUseShellOperationsStream } from "./usePlatformRealtime";

describe("Platform realtime ownership", () => {
  it("keeps the shared shell stream on normal Platform pages", () => {
    expect(shouldUseShellOperationsStream(true, "/platform/tenants")).toBe(true);
    expect(shouldUseShellOperationsStream(true, "/platform/security")).toBe(true);
  });

  it("keeps the shell as the sole stream owner on Operations", () => {
    expect(shouldUseShellOperationsStream(true, "/platform/operations")).toBe(true);
  });

  it("does not connect before Platform access is allowed", () => {
    expect(shouldUseShellOperationsStream(false, "/platform/tenants")).toBe(false);
    expect(shouldUseShellOperationsStream(false, "/platform/operations")).toBe(false);
  });

  it("does not retry permanent missing-route failures", () => {
    expect(isTerminalPlatformRealtimeStatus(404)).toBe(true);
    expect(isTerminalPlatformRealtimeStatus(405)).toBe(true);
    expect(isTerminalPlatformRealtimeStatus(401)).toBe(false);
    expect(isTerminalPlatformRealtimeStatus(429)).toBe(false);
    expect(isTerminalPlatformRealtimeStatus(500)).toBe(false);
    expect(isTerminalPlatformRealtimeStatus(503)).toBe(false);
  });
});
