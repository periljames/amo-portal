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

import {
  checkoutUrlFromJob,
  saasSettingsApi,
  waitForSaaSJob,
  type SaaSAdminJob,
} from "./saasSettings";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function job(status: string, result: Record<string, unknown> | null = null): SaaSAdminJob {
  return {
    id: "job-1",
    queue_name: "billing",
    job_type: "STRIPE_CREATE_CHECKOUT_SESSION",
    status,
    priority: 1,
    attempt_count: 1,
    max_attempts: 5,
    result,
  };
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

  it("polls the tenant-scoped job until Stripe checkout succeeds", async () => {
    cachedUser.value = { id: "root-1", is_superuser: true, is_amo_admin: false };
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(job("RUNNING")))
      .mockResolvedValueOnce(jsonResponse(job("SUCCEEDED", {
        checkout_url: "https://checkout.stripe.com/c/pay/cs_test_123",
      })));

    const completed = await waitForSaaSJob("job/one", "tenant/one", {
      timeoutMs: 2_000,
      pollIntervalMs: 50,
    });

    expect(completed.status).toBe("SUCCEEDED");
    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://api.example.test/platform/tenant-saas/jobs/job%2Fone?tenant_id=tenant%2Fone",
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("returns only an HTTPS checkout URL from a successful job", () => {
    expect(checkoutUrlFromJob(job("SUCCEEDED", {
      checkout_url: "https://checkout.stripe.com/c/pay/cs_test_123",
    }))).toBe("https://checkout.stripe.com/c/pay/cs_test_123");
    expect(checkoutUrlFromJob(job("SUCCEEDED", {
      checkout_url: "http://checkout.stripe.com/insecure",
    }))).toBeNull();
    expect(checkoutUrlFromJob(job("RUNNING", {
      checkout_url: "https://checkout.stripe.com/not-ready",
    }))).toBeNull();
  });
});
