import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./branding", () => ({ clearBrandContext: vi.fn(), setBrandContext: vi.fn() }));
vi.mock("./runtimeMode", () => ({ setPortalDataMode: vi.fn() }));
vi.mock("./config", () => ({ getApiBaseUrl: () => "http://portal.test" }));
vi.mock("./portalConnectivity", () => ({
  getPortalConnectivity: () => ({ state: "ONLINE" }), probePortalReadiness: vi.fn(),
}));

function storage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  };
}

beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("localStorage", storage());
  vi.stubGlobal("sessionStorage", storage());
  vi.stubGlobal("BroadcastChannel", undefined);
  vi.stubGlobal("window", Object.assign(new EventTarget(), { setTimeout, clearTimeout }));
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("session recovery", () => {
  it("uses Web Locks and installs the fresh token after a successful refresh", async () => {
    const request = vi.fn(async (_name: string, callback: () => Promise<unknown>) => callback());
    vi.stubGlobal("navigator", { locks: { request } });
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      access_token: "new-token", expires_in: 3600, user: null, amo: null, department: null,
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    const auth = await import("./auth");
    auth.saveToken("old-token");
    const result = await auth.recoverSession();
    expect(request).toHaveBeenCalledOnce();
    expect(result?.access_token).toBe("new-token");
    expect(auth.getTokenSecondsRemaining()).toBeGreaterThan(3590);
  });

  it("does not restore a session after logout while refresh is in flight", async () => {
    let finish!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const auth = await import("./auth");
    auth.saveToken("old-token");
    const pending = auth.recoverSession();
    auth.logout();
    finish(new Response(JSON.stringify({ access_token: "new-token", expires_in: 3600 }), { status: 200 }));
    expect(await pending).toBeNull();
    expect(auth.getToken()).toBeNull();
  });

  it("coalesces 1000 recovery triggers and respects a 429 cooldown", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 429, headers: { "Retry-After": "60" } }));
    vi.stubGlobal("fetch", fetch);
    const auth = await import("./auth");
    auth.saveToken("old-token");
    await Promise.all(Array.from({ length: 1000 }, () => auth.recoverSession()));
    expect(fetch).toHaveBeenCalledTimes(1);
    await auth.recoverSession();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(auth.getToken()).toBe("old-token");
    expect(auth.hasRecoverableSession()).toBe(true);
  });

  it("uses server lifetime when the client clock is hours ahead, including reload", async () => {
    const auth = await import("./auth");
    const serverNow = Math.floor(Date.now() / 1000);
    const token = `header.${btoa(JSON.stringify({ exp: serverNow + 3600 }))}.signature`;
    vi.spyOn(Date, "now").mockReturnValue((serverNow + 7200) * 1000);
    auth.saveToken(token, 3600);
    expect(auth.getTokenSecondsRemaining()).toBe(3600);
    vi.resetModules();
    const reloaded = await import("./auth");
    expect(reloaded.getTokenSecondsRemaining()).toBe(3600);
    vi.spyOn(Date, "now").mockReturnValue((serverNow + 7500) * 1000);
    expect(reloaded.getTokenSecondsRemaining()).toBe(3300);
  });

  it("keeps cached authority during transport failures and suppresses immediate retries", async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError("network failure"));
    vi.stubGlobal("fetch", fetch);
    const auth = await import("./auth");
    auth.saveToken("old-token");
    await auth.recoverSession();
    await auth.recoverSession();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(auth.hasRecoverableSession()).toBe(true);
  });
});
