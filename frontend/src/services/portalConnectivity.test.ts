import { describe, expect, it } from "vitest";

import { getPortalConnectivity, notePortalResponse } from "./portalConnectivity";

function response(status: number, url: string): Response {
  const value = new Response(null, { status });
  Object.defineProperty(value, "url", { configurable: true, value: url });
  return value;
}

describe("portal dependency recovery", () => {
  it("does not let a process-only success clear a dependency outage", () => {
    notePortalResponse(response(503, "http://127.0.0.1:8080/quality/audits"));
    expect(getPortalConnectivity().state).toBe("DEGRADED");

    notePortalResponse(response(200, "http://127.0.0.1:8080/time"));
    expect(getPortalConnectivity().state).toBe("DEGRADED");

    notePortalResponse(response(200, "http://127.0.0.1:8080/quality/audits"));
    expect(getPortalConnectivity().state).toBe("ONLINE");
  });
});
