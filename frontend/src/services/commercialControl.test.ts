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
  authHeaders: () => new Headers({ Authorization: "Bearer commercial-token" }),
  extendSessionIfNeeded,
  handleAuthFailure,
  markSessionActivity,
}));

vi.mock("./config", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));

import { commercialApi } from "./commercialControl";

describe("canonical commercial control API", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    extendSessionIfNeeded.mockReset();
    extendSessionIfNeeded.mockReturnValue(null);
    handleAuthFailure.mockReset();
    markSessionActivity.mockReset();
  });

  it("rejects ALL before issuing a request", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    await expect(commercialApi.summary("ALL" as never)).rejects.toThrow(
      "Platform data mode must be REAL or DEMO.",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("preserves authorization and active-session extension", async () => {
    const extension = Promise.resolve(null);
    extendSessionIfNeeded.mockReturnValue(extension);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ data_mode: "REAL", subscriptions: {} }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await commercialApi.summary("REAL");

    expect(extendSessionIfNeeded).toHaveBeenCalledWith(
      "commercial-control:/platform/commercial/summary?data_mode=REAL",
    );
    const [, init] = fetchMock.mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Bearer commercial-token");
    expect(headers.get("Accept")).toBe("application/json");
    expect(markSessionActivity).toHaveBeenCalledWith(
      "commercial-control:success:/platform/commercial/summary?data_mode=REAL",
    );
  });

  it("clears a rejected token without a manual logout request", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 401 }));

    await expect(commercialApi.modules()).rejects.toThrow(
      "Session expired. Please sign in again.",
    );
    expect(handleAuthFailure).toHaveBeenCalledWith("commercial-control-unauthorized");
  });

  it("sends one structured invoice mutation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "invoice-1", lines: [] }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );

    await commercialApi.createInvoice("amo/one", {
      currency: "KES",
      idempotency_key: "invoice-action-1",
      lines: [{ description: "Quality", quantity: 2, unit_amount_cents: 1000 }],
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/platform/commercial/tenants/amo%2Fone/invoices",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      currency: "KES",
      idempotency_key: "invoice-action-1",
      lines: [{ description: "Quality", quantity: 2, unit_amount_cents: 1000 }],
    });
  });

  it("uses the persistent password-reset endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "user-1", must_change_password: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await commercialApi.forcePasswordReset("user/one", "Security review");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/platform/commercial/users/user%2Fone/force-password-reset",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
