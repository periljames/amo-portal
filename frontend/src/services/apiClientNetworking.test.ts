import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest, clearApiResponseCache } from "./apiClient";
import { installOfflineBrowser } from "../test/offlineBrowser";

const state = vi.hoisted(() => ({ user: "one", fetch: vi.fn() }));
vi.mock("./auth", () => ({
  authHeaders: () => ({}), getCachedUser: () => ({ id: state.user, amo_id: "amo" }),
  getContext: () => ({ amoCode: "amo" }), ensureAuthenticatedRequestAllowed: () => true,
  getToken: () => "token", handleAuthFailure: vi.fn(),
}));
vi.mock("./offlineHttp", async (original) => ({
  ...await original<typeof import("./offlineHttp")>(), portalFetch: state.fetch,
}));

beforeEach(() => { installOfflineBrowser(); state.user = "one"; state.fetch.mockReset(); clearApiResponseCache(); });
afterEach(() => vi.unstubAllGlobals());
function response() { return new Response("{}", { headers: { "Content-Type": "application/json" } }); }

describe("portal networking queue", () => {
  it("does not replay an upload after an ambiguous connection failure", async () => {
    state.fetch.mockRejectedValue(new TypeError("Failed to fetch"));
    const body = new FormData(); body.set("file", new Blob(["evidence"]), "evidence.txt");
    await expect(apiRequest("/network-test/upload", { method: "POST", body })).rejects.toThrow("Failed to fetch");
    expect(state.fetch).toHaveBeenCalledTimes(1);
  });
  it("uses a file transfer budget for multipart uploads", async () => {
    state.fetch.mockResolvedValue(response());
    const body = new FormData(); body.set("file", new Blob(["evidence"]), "evidence.txt");
    await apiRequest("/network-test/upload", { method: "POST", body });
    expect(state.fetch.mock.calls[0][1].timeoutMs).toBeGreaterThan(290_000);
  });
  it("shows the actionable message from a structured workflow failure", async () => {
    state.fetch.mockResolvedValue(new Response(JSON.stringify({ detail: { code: "AUDIT_NOTICE_MEETINGS_REQUIRED", message: "Save both meetings before generating the notice." } }), { status: 409, headers: { "Content-Type": "application/json" } }));
    await expect(apiRequest("/network-test/notice", { method: "POST", body: "{}" })).rejects.toThrow("Save both meetings before generating the notice.");
  });
  it("persists fresh-every-time module reads unless offline caching is explicitly disabled", async () => {
    state.fetch.mockImplementation(async () => response());
    await apiRequest("/api/maintenance/amo/procurement/suppliers", { cacheTtlMs: 0 });
    expect(state.fetch.mock.calls[0][1].offline.cache).toBe(true);
    await apiRequest("/network-test/private", { cacheTtlMs: 0, offline: { cache: false } });
    expect(state.fetch.mock.calls[1][1].offline.cache).toBe(false);
  });
  it("cancels queued navigation without sending its request", async () => {
    const release: Array<(value: Response) => void> = [];
    state.fetch.mockImplementation(() => new Promise<Response>((resolve) => release.push(resolve)));
    const active = Array.from({ length: 6 }, (_, index) => apiRequest(`/network-test/${index}`, { cacheTtlMs: 0 }));
    await vi.waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(6));
    const controller = new AbortController();
    const waiting = apiRequest("/network-test/cancelled", { signal: controller.signal, cacheTtlMs: 0 });
    const rejected = expect(waiting).rejects.toMatchObject({ name: "AbortError" });
    controller.abort();
    await rejected;
    release.forEach((resolve) => resolve(response()));
    await Promise.all(active);
    expect(state.fetch).toHaveBeenCalledTimes(6);
  });
  it("opens fresh cached data even when every network slot is occupied", async () => {
    state.fetch.mockResolvedValueOnce(response());
    await apiRequest("/fast-cache/records");
    const release: Array<(value: Response) => void> = [];
    state.fetch.mockImplementation(() => new Promise<Response>((resolve) => release.push(resolve)));
    const active = Array.from({ length: 6 }, (_, index) => apiRequest(`/fast-cache/slow/${index}`, { cacheTtlMs: 0 }));
    await vi.waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(7));
    await expect(apiRequest("/fast-cache/records")).resolves.toEqual({});
    expect(state.fetch).toHaveBeenCalledTimes(7);
    release.forEach((resolve) => resolve(response()));
    await Promise.all(active);
  });
  it("bounds queue waiting by the request deadline without sending an expired request", async () => {
    const release: Array<(value: Response) => void> = [];
    state.fetch.mockImplementation(() => new Promise<Response>((resolve) => release.push(resolve)));
    const active = Array.from({ length: 6 }, (_, index) => apiRequest(`/network-deadline/${index}`, { cacheTtlMs: 0 }));
    await vi.waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(6));
    await expect(apiRequest("/network-deadline/expired", { cacheTtlMs: 0, timeoutMs: 20 })).rejects.toThrow("waiting for a network slot");
    release.forEach((resolve) => resolve(response()));
    await Promise.all(active);
    expect(state.fetch).toHaveBeenCalledTimes(6);
  });
  it("deducts time spent queued from the transport timeout", async () => {
    const release: Array<(value: Response) => void> = [];
    state.fetch.mockImplementation(() => new Promise<Response>((resolve) => release.push(resolve)));
    const active = Array.from({ length: 6 }, (_, index) => apiRequest(`/network-budget/${index}`, { cacheTtlMs: 0 }));
    await vi.waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(6));
    const waiting = apiRequest("/network-budget/waiting", { cacheTtlMs: 0, timeoutMs: 1000 });
    await new Promise((resolve) => setTimeout(resolve, 30));
    release.forEach((resolve) => resolve(response()));
    await vi.waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(7));
    expect(state.fetch.mock.calls[6][1].timeoutMs).toBeLessThan(1000);
    release[6](response());
    await Promise.all([...active, waiting]);
  });
  it("does not send an old account's waiting request after account switching", async () => {
    const release: Array<(value: Response) => void> = [];
    state.fetch.mockImplementation(() => new Promise<Response>((resolve) => release.push(resolve)));
    const requests = Array.from({ length: 7 }, (_, index) => apiRequest(`/network-test/${index}`, { cacheTtlMs: 0 }));
    const all = Promise.allSettled(requests);
    await vi.waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(6));
    state.user = "two";
    release.forEach((resolve) => resolve(response()));
    expect((await all).every((result) => result.status === "rejected")).toBe(true);
    expect(state.fetch).toHaveBeenCalledTimes(6);
  });
  it("keeps a successful save successful when optional session cache is blocked", async () => {
    Object.defineProperty(window, "sessionStorage", { configurable: true, get: () => { throw new Error("blocked"); } });
    state.fetch.mockResolvedValue(response());
    await expect(apiRequest("/network-test/save", { method: "POST", body: "{}" })).resolves.toEqual({});
  });
});
