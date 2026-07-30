import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

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

import { resolvePostLoginReturnTarget } from "../app/loginRedirect";
import { shouldProxyDevApi, shouldServePlatformSpa } from "./devProxyRouting";
import { platformConsoleApi } from "./platformConsole";
import { platformApi } from "./platformControl";

const platformSharedSource = readFileSync(
  fileURLToPath(new URL("../pages/platform/components/PlatformShared.tsx", import.meta.url)),
  "utf8",
);

describe("platform SaaS control API", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    endSession.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("hydrates the authoritative platform user before denying access", () => {
    expect(platformSharedSource).toContain("fetchCurrentUser()");
    expect(platformSharedSource).toContain('accessState === "checking"');
    expect(platformSharedSource).toContain('endSession("manual")');
    expect(platformSharedSource).toContain("Sign in with platform account");
  });

  it("does not return a tenant login to a denied platform route", () => {
    const handlerStart = platformSharedSource.indexOf("const signInWithPlatformAccount");
    const handlerEnd = platformSharedSource.indexOf("\n  };", handlerStart);
    const signInHandler = platformSharedSource.slice(handlerStart, handlerEnd + 5);

    expect(handlerStart).toBeGreaterThanOrEqual(0);
    expect(handlerEnd).toBeGreaterThan(handlerStart);
    expect(signInHandler).toContain('navigate("/login", { replace: true })');
    expect(signInHandler).not.toContain("state:");
    expect(signInHandler).not.toContain("location.pathname");
  });

  it("allows verified platform users to return to normalized platform pages", () => {
    expect(resolvePostLoginReturnTarget("/platform/security?tab=alerts", true)).toBe(
      "/platform/security?tab=alerts",
    );
    expect(resolvePostLoginReturnTarget("/Platform/security?tab=alerts", true)).toBe(
      "/Platform/security?tab=alerts",
    );
  });

  it("blocks tenant users from raw, case-variant, and encoded platform routes", () => {
    expect(resolvePostLoginReturnTarget("/platform/control", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("/platform/integrations?tab=email", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("/Platform/control", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("/%70latform/control", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("/PLATFORM/%63ontrol", false)).toBeNull();
  });

  it("rejects login loops, external targets, and malformed encodings", () => {
    expect(resolvePostLoginReturnTarget("/login", true)).toBeNull();
    expect(resolvePostLoginReturnTarget("/LOGIN", true)).toBeNull();
    expect(resolvePostLoginReturnTarget("/maintenance/safarilink/login", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("/maintenance/safarilink/%6Cogin", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("https://example.com/platform/control", true)).toBeNull();
    expect(resolvePostLoginReturnTarget("//example.com/platform/control", true)).toBeNull();
    expect(resolvePostLoginReturnTarget("/%2Fexample.com/platform/control", true)).toBeNull();
    expect(resolvePostLoginReturnTarget("/%E0%A4%A", false)).toBeNull();
  });

  it("keeps valid tenant return routes available to tenant users", () => {
    expect(resolvePostLoginReturnTarget("/maintenance/safarilink/quality/inbox", false)).toBe(
      "/maintenance/safarilink/quality/inbox",
    );
  });

  it("keeps direct platform page navigation in the SPA", () => {
    expect(shouldServePlatformSpa("GET", "/platform/integrations", "text/html,application/xhtml+xml")).toBe(true);
    expect(shouldServePlatformSpa("HEAD", "/platform/security?tab=alerts", "text/html")).toBe(true);
  });

  it("continues proxying platform API fetches", () => {
    expect(shouldServePlatformSpa("GET", "/platform/integrations/summary", "application/json")).toBe(false);
    expect(shouldServePlatformSpa("POST", "/platform/commands", "text/html")).toBe(false);
    expect(shouldServePlatformSpa("GET", "/api/chat/threads", "text/html")).toBe(false);
  });

  it("proxies canonical Document Control workspace requests to FastAPI", () => {
    expect(shouldProxyDevApi("/doc-control/workspace/t/safarilink/documents?per_page=100")).toBe(true);
    expect(shouldProxyDevApi("/doc-control/workspace/t/safarilink/dashboard")).toBe(true);
    expect(shouldProxyDevApi("/manuals/t/safarilink/manual-1/rev/rev-1/reader-metadata")).toBe(true);
    expect(shouldProxyDevApi("/maintenance/safarilink/document-control/library")).toBe(false);
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

  it("loads the superadmin console bootstrap with platform authentication", async () => {
    const payload = { active_tenants: 8, queue_depth: 3 };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(platformConsoleApi.bootstrap()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/platform/console/bootstrap",
      expect.objectContaining({
        method: "GET",
        credentials: "include",
        headers: expect.objectContaining({
          Authorization: "Bearer platform-token",
          Accept: "application/json",
        }),
      }),
    );
  });

  it("encodes superadmin search terms and result limits", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await platformConsoleApi.search("James & AMO", 7);

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/platform/console/search?q=James+%26+AMO&limit=7",
      expect.any(Object),
    );
  });

  it("invalidates the session when superadmin console authorization expires", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 401 }));

    await expect(platformConsoleApi.bootstrap()).rejects.toThrow("Session expired. Please sign in again.");
    expect(endSession).toHaveBeenCalledWith("manual");
  });
});
