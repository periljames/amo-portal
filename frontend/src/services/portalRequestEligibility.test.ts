import { describe, expect, it } from "vitest";

import { isPortalRequestNetworkEligible } from "./portalRequestEligibility";

describe("portal request network eligibility", () => {
  it.each(["ONLINE", "DEGRADED", "OFFLINE", "RECOVERING"] as const)(
    "allows browser-online GET requests while shared connectivity is %s",
    (state) => {
      expect(isPortalRequestNetworkEligible("GET", state, true)).toBe(true);
    },
  );

  it("blocks GET requests when the browser itself reports offline", () => {
    expect(isPortalRequestNetworkEligible("GET", "ONLINE", false)).toBe(false);
  });

  it("blocks GET requests after the session expires", () => {
    expect(isPortalRequestNetworkEligible("GET", "SESSION_EXPIRED", true)).toBe(false);
  });

  it.each(["POST", "PUT", "PATCH", "DELETE"] as const)(
    "allows %s mutations while the reachable API is DEGRADED",
    (method) => {
      expect(isPortalRequestNetworkEligible(method, "DEGRADED", true)).toBe(true);
    },
  );

  it.each(["OFFLINE", "RECOVERING", "SESSION_EXPIRED"] as const)(
    "blocks mutations while shared connectivity is %s",
    (state) => {
      expect(isPortalRequestNetworkEligible("PATCH", state, true)).toBe(false);
    },
  );

  it("allows mutations when the portal is ONLINE", () => {
    expect(isPortalRequestNetworkEligible("PATCH", "ONLINE", true)).toBe(true);
  });

  it("blocks mutations when the browser itself reports offline", () => {
    expect(isPortalRequestNetworkEligible("PATCH", "DEGRADED", false)).toBe(false);
  });
});
