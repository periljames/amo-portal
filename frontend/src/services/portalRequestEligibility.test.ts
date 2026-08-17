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

  it.each(["DEGRADED", "OFFLINE", "RECOVERING", "SESSION_EXPIRED"] as const)(
    "blocks mutations until ONLINE when shared connectivity is %s",
    (state) => {
      expect(isPortalRequestNetworkEligible("POST", state, true)).toBe(false);
    },
  );

  it("allows mutations only once the portal is ONLINE", () => {
    expect(isPortalRequestNetworkEligible("POST", "ONLINE", true)).toBe(true);
  });
});
