import { describe, expect, it } from "vitest";

import { resolveManualRouteContext } from "./context";

describe("resolveManualRouteContext", () => {
  it("uses tenant slug route for /t pages", () => {
    const ctx = resolveManualRouteContext({ tenantSlug: "safarilink", manualId: "m1", revId: "r1" });
    expect(ctx.tenant).toBe("safarilink");
    expect(ctx.basePath).toBe("/t/safarilink/manuals");
  });

  it("uses amoCode route for maintenance pages", () => {
    const ctx = resolveManualRouteContext({ amoCode: "safarilink", docId: "m1", revId: "r1" });
    expect(ctx.tenant).toBe("safarilink");
    expect(ctx.basePath).toBe("/maintenance/safarilink/manuals");
  });
});
