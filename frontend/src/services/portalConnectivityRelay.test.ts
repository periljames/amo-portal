import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installOfflineBrowser } from "../test/offlineBrowser";

beforeEach(() => {
  vi.resetModules(); vi.useFakeTimers(); installOfflineBrowser();
  vi.stubGlobal("navigator", { onLine: true });
});
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("readiness over a public relay", () => {
  it("accepts a healthy four-second relay response", async () => {
    const fetch = vi.fn((_path, init) => new Promise<Response>((resolve, reject) => {
      const timer = setTimeout(() => resolve(new Response('{"ready":true,"db":true}', { headers: { "Content-Type": "application/json" } })), 4000);
      init.signal.addEventListener("abort", () => { clearTimeout(timer); reject(init.signal.reason); });
    }));
    vi.stubGlobal("fetch", fetch);
    const { probePortalReadiness } = await import("./portalConnectivity");
    const probe = probePortalReadiness(true);
    await vi.advanceTimersByTimeAsync(4001);
    expect((await probe).state).toBe("ONLINE");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("keeps an ambiguous probe timeout advisory while the browser is online", async () => {
    vi.stubGlobal("fetch", vi.fn((_path, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener("abort", () => reject(init.signal.reason));
    })));
    const { probePortalReadiness } = await import("./portalConnectivity");
    const probe = probePortalReadiness(true);
    await vi.advanceTimersByTimeAsync(8001);
    expect((await probe).state).toBe("DEGRADED");
  });

  it("still blocks a browser-confirmed disconnection", async () => {
    vi.stubGlobal("navigator", { onLine: false });
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const { probePortalReadiness } = await import("./portalConnectivity");
    expect((await probePortalReadiness(true)).state).toBe("OFFLINE");
    expect(fetch).not.toHaveBeenCalled();
  });
});
