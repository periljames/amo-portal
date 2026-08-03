import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  extendSessionIfNeeded,
  handleAuthFailure,
  markSessionActivity,
} = vi.hoisted(() => ({
  extendSessionIfNeeded: vi.fn(),
  handleAuthFailure: vi.fn(),
  markSessionActivity: vi.fn(),
}));

vi.mock("./auth", () => ({
  authHeaders: () => new Headers({ Authorization: "Bearer phase4-token" }),
  extendSessionIfNeeded,
  handleAuthFailure,
  markSessionActivity,
}));

vi.mock("./config", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));

import { phase4Api } from "./platformPhase4";

describe("Phase 4 platform operations", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    extendSessionIfNeeded.mockReset();
    extendSessionIfNeeded.mockReturnValue(null);
    handleAuthFailure.mockReset();
    markSessionActivity.mockReset();
  });

  it("sends an explicit REAL environment for security alerts", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ items: [], data_mode: "REAL" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await phase4Api.securityAlerts({ data_mode: "REAL", severity: "CRITICAL" });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/platform/phase4/security/alerts?data_mode=REAL&severity=CRITICAL",
      expect.objectContaining({ credentials: "include" }),
    );
    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer phase4-token");
  });

  it("keeps DEMO audit queries isolated", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ items: [], data_mode: "DEMO" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await phase4Api.securityAudit({ data_mode: "DEMO", tenant_id: "demo/one" });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/platform/phase4/security/audit?data_mode=DEMO&tenant_id=demo%2Fone",
      expect.any(Object),
    );
  });

  it("records reasons for maintenance transitions", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "mw-1", status: "ACTIVE" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await phase4Api.transitionMaintenance("mw/1", "ACTIVE", "Approved window");

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      status: "ACTIVE",
      reason: "Approved window",
    });
  });

  it("starts canonical tenant support sessions", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "support-1", status: "PENDING" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await phase4Api.startSupportSession("tenant/one", {
      access_level: "ADMIN",
      reason: "Tenant-approved investigation",
      minutes: 45,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/platform/phase4/tenants/tenant%2Fone/support-sessions",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("clears rejected authentication without server logout recursion", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 401 }));

    await expect(phase4Api.infrastructureCapabilities()).rejects.toThrow(
      "Session expired. Please sign in again.",
    );
    expect(handleAuthFailure).toHaveBeenCalledWith("phase4-unauthorized");
  });
});
