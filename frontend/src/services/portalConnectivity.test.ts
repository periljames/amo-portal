import { describe, expect, it } from "vitest";

import { getPortalConnectivity, notePortalResponse } from "./portalConnectivity";

function response(status: number, url: string, headers?: HeadersInit): Response {
  const value = new Response(null, { status, headers });
  Object.defineProperty(value, "url", { configurable: true, value: url });
  return value;
}

describe("portal dependency recovery", () => {
  it("does not let a process-only success clear a dependency outage", () => {
    notePortalResponse(response(503, "http://127.0.0.1:8080/quality/audits", { "X-Portal-Readiness": "offline" }));
    expect(getPortalConnectivity().state).toBe("DEGRADED");

    notePortalResponse(response(200, "http://127.0.0.1:8080/time"));
    expect(getPortalConnectivity().state).toBe("DEGRADED");

    notePortalResponse(response(200, "http://127.0.0.1:8080/quality/audits"));
    expect(getPortalConnectivity().state).toBe("ONLINE");
  });

  it("keeps module failures local", () => {
    notePortalResponse(response(200, "http://127.0.0.1:8080/auth/me"));
    for (const status of [500, 503]) {
      notePortalResponse(response(status, "http://127.0.0.1:8080/quality/audits"));
      expect(getPortalConnectivity().state).toBe("ONLINE");
    }
  });
});
