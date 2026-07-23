import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { endSession } = vi.hoisted(() => ({ endSession: vi.fn() }));

vi.mock("./auth", () => ({
  authHeaders: () => ({ Authorization: "Bearer platform-token" }),
  endSession,
  getCachedUser: () => ({ id: "root", email: "root@example.test", is_superuser: true }),
}));

vi.mock("./config", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));

import { platformApi } from "./platformControl";

describe("platform SaaS control API", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    endSession.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("encodes tenant identifiers and sends module updates as one audited batch", async () => {
    const response = { items: [{ id: "sub-1", amo_id: "tenant/one", module_code: "quality", status: "ENABLED" }] };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(response), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(platformApi.updateTenantModules(
      "tenant/one",
      [{ module_code: "quality", status: "ENABLED", plan_code: "STANDARD" }],
      "Subscription approved",
    )).resolves.toEqual(response);

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/platform/saas/tenants/tenant%2Fone/modules",
      expect.objectContaining({
        method: "PATCH",
        credentials: "include",
        headers: expect.any(Headers),
      }),
    );
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      changes: [{ module_code: "quality", status: "ENABLED", plan_code: "STANDARD" }],
      reason: "Subscription approved",
    });
  });

  it("sends provider secrets only in an explicit update request", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ provider: "openai", status: "CONFIGURED", has_secret: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await platformApi.updateSaasProvider("openai", {
      config: { model: "configured-model" },
      secret: { api_key: "server-only-key" },
      enabled: true,
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      config: { model: "configured-model" },
      secret: { api_key: "server-only-key" },
      enabled: true,
    });
  });

  it("surfaces backend validation detail", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "eTIMS adapter is not certified" }), {
        status: 400,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(platformApi.fiscalizeInvoice("invoice-1", "etims_oscu"))
      .rejects.toThrow("eTIMS adapter is not certified");
  });

  it("invalidates the session on 401", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 401 }));

    await expect(platformApi.saasCapabilities())
      .rejects.toThrow("Session expired. Please sign in again.");
    expect(endSession).toHaveBeenCalledWith("manual");
  });

  it("returns a deterministic write timeout", async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));

    const pending = platformApi.createModulePrice({ module_code: "quality", amount_cents: 1000 });
    const assertion = expect(pending).rejects.toThrow("Platform request timed out after 25 seconds.");
    await vi.advanceTimersByTimeAsync(25_000);
    await assertion;
  });
});
