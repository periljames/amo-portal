import { describe, expect, it } from "vitest";

import { shouldUseShellOperationsStream } from "./usePlatformRealtime";

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
});
