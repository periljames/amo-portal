import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("document", { querySelector: () => ({ src: "https://portal.test/assets/index-old.js" }), querySelectorAll: () => [{ href: "https://portal.test/assets/index-old.css" }] });
  vi.stubGlobal("location", { origin: "https://portal.test", reload: vi.fn() });
  vi.stubGlobal("window", { setTimeout, clearTimeout });
});
afterEach(() => { vi.unstubAllGlobals(); });
const manifest = (entry: string, style = "old") => new Response(JSON.stringify({ urls: ["/", `/assets/index-${entry}.js`, `/assets/index-${style}.css`, "/assets/framework-vendor-1.js"] }));

describe("portal release updates", () => {
  it("detects a stylesheet-only release even when JavaScript has not changed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(manifest("old", "new")));
    const release = await import("./portalRelease");
    await release.checkPortalRelease();
    expect(release.getPortalRelease().available).toBe(true);
    expect(location.reload).not.toHaveBeenCalled();
  });
  it("detects a superseded open tab without automatically reloading or touching form data", async () => {
    const fetch = vi.fn().mockResolvedValue(manifest("new")); vi.stubGlobal("fetch", fetch);
    const release = await import("./portalRelease");
    await release.checkPortalRelease();
    expect(release.getPortalRelease()).toEqual({ available: true, checking: false, error: null });
    expect(fetch.mock.calls[0][1].cache).toBe("no-store");
    expect(location.reload).not.toHaveBeenCalled();
  });
  it("recognizes the currently loaded build and rejects incomplete release manifests", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(manifest("old")).mockResolvedValueOnce(new Response('{"urls":[]}')));
    const release = await import("./portalRelease");
    await release.checkPortalRelease(); expect(release.getPortalRelease().available).toBe(false);
    await release.checkPortalRelease(); expect(release.getPortalRelease().error).toMatch(/not ready/);
  });
  it("keeps a known available update when a subsequent check loses connectivity", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(manifest("new")).mockRejectedValueOnce(new TypeError("Offline")));
    const release = await import("./portalRelease");
    await release.checkPortalRelease(); await release.checkPortalRelease();
    expect(release.getPortalRelease().available).toBe(true);
    expect(release.getPortalRelease().checking).toBe(false);
    expect(location.reload).not.toHaveBeenCalled();
  });
  it("reloads only after the service worker confirms the new canonical shell was cached", async () => {
    let message: (data: unknown, ports: MessagePort[]) => void = () => {};
    vi.stubGlobal("navigator", { serviceWorker: { getRegistration: async () => ({ active: { postMessage: (data: unknown, ports: MessagePort[]) => message(data, ports) } }) } });
    message = (data, ports) => { expect(data).toEqual({ type: "REFRESH_PORTAL_SHELL" }); expect(location.reload).not.toHaveBeenCalled(); ports[0].postMessage({ ok: true }); };
    const release = await import("./portalRelease"); await release.reloadPortalRelease();
    expect(location.reload).toHaveBeenCalledOnce();
  });
  it("leaves the current page open when the new shell cannot be fetched", async () => {
    vi.stubGlobal("navigator", { serviceWorker: { getRegistration: async () => ({ active: { postMessage: (_: unknown, ports: MessagePort[]) => ports[0].postMessage({ ok: false }) } }) } });
    const release = await import("./portalRelease");
    await expect(release.reloadPortalRelease()).rejects.toThrow(/current page remains open/);
    expect(location.reload).not.toHaveBeenCalled();
  });
});
