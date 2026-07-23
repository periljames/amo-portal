import { beforeEach, describe, expect, it, vi } from "vitest";

const cachedUser = vi.hoisted(() => ({
  value: { id: "admin-1", is_superuser: false, is_amo_admin: true },
}));

vi.mock("./auth", () => ({
  authHeaders: () => ({ Authorization: "Bearer admin-token" }),
  endSession: vi.fn(),
  getCachedUser: () => cachedUser.value,
}));

vi.mock("./config", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));

import { saasSettingsApi } from "./saasSettings";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("SaaS administration client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    cachedUser.value = { id: "admin-1", is_superuser: false, is_amo_admin: true };
  });

  it("never sends an arbitrary tenant id for an AMO administrator", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ providers: [] }));

    await saasSettingsApi.setup("another-tenant");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/platform/tenant-saas/setup",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("allows a superadmin to select an explicit tenant scope", async () => {
    cachedUser.value = { id: "root-1", is_superuser: true, is_amo_admin: false };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ providers: [] }));

    await saasSettingsApi.setup("tenant/one");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/platform/tenant-saas/setup?tenant_id=tenant%2Fone",
      expect.any(Object),
    );
  });

  it("sends provider configuration and audit reason to the tenant pipeline", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ provider: "stripe" }));

    await saasSettingsApi.updateProvider("stripe", {
      config: { environment: "production" },
      secret: { webhook_secret: "whsec_test" },
      reason: "Rotate tenant Stripe endpoint secret",
      enabled: true,
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.test/platform/tenant-saas/providers/stripe");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toMatchObject({
      reason: "Rotate tenant Stripe endpoint secret",
      secret: { webhook_secret: "whsec_test" },
    });
  });

  it("links checkout actions to the backend job pipeline", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: "job-1" }, 202));

    await saasSettingsApi.checkout("price-1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.test/platform/tenant-saas/checkout");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toMatchObject({ module_price_id: "price-1" });
  });
});
