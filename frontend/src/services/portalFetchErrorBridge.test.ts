import { describe, expect, it } from "vitest";

import { isPlatformOpsUrl } from "./portalFetchErrorBridge";

describe("isPlatformOpsUrl", () => {
  it("recognises the Operations gateway paths that must not kill portal sessions", () => {
    expect(isPlatformOpsUrl("/ops/v1/bootstrap?data_mode=REAL")).toBe(true);
    expect(isPlatformOpsUrl("/ops/v1/live?data_mode=REAL")).toBe(true);
    expect(isPlatformOpsUrl("http://127.0.0.1:5173/ops/v1/bootstrap")).toBe(true);
    expect(isPlatformOpsUrl("/ops")).toBe(true);
  });

  it("does not treat tenant API or console paths as Operations gateway traffic", () => {
    expect(isPlatformOpsUrl("/auth/me")).toBe(false);
    expect(isPlatformOpsUrl("/auth/refresh")).toBe(false);
    expect(isPlatformOpsUrl("/platform/console/bootstrap")).toBe(false);
    expect(isPlatformOpsUrl("/api/events")).toBe(false);
  });
});
