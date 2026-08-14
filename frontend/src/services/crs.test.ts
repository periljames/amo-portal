import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  extend: vi.fn(),
  failure: vi.fn(),
  portalFetch: vi.fn(),
  token: "test-token",
}));

vi.mock("./auth", () => ({
  authHeaders: (extra?: HeadersInit) => {
    const headers = new Headers(extra);
    headers.set("Authorization", `Bearer ${mocks.token}`);
    return headers;
  },
  extendSessionIfNeeded: mocks.extend,
  handleAuthFailure: mocks.failure,
  markSessionActivity: vi.fn(),
}));
vi.mock("./offlineHttp", () => ({ portalFetch: mocks.portalFetch }));
vi.mock("./adminPageTenantScope", () => ({ beginAdminPageTenantScope: vi.fn(() => null), completeAdminPageTenantScope: vi.fn() }));
vi.mock("./loading", () => ({ beginBackgroundLoading: vi.fn(), beginLoading: vi.fn(), endBackgroundLoading: vi.fn(), endLoading: vi.fn() }));

import { apiGet } from "./crs";

describe("authenticated API request helper", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.extend.mockReturnValue(null);
    mocks.portalFetch.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
  });

  it("adds the current bearer token to Training Operating System requests", async () => {
    await expect(apiGet("/training/operating/access")).resolves.toEqual({ ok: true });
    const [, init] = mocks.portalFetch.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer test-token");
  });

  it("waits for a near-expiry session extension before sending the request", async () => {
    let release: (() => void) | undefined;
    mocks.extend.mockReturnValue(new Promise<void>((resolve) => { release = resolve; }));
    const pending = apiGet("/training/operating/access");
    await Promise.resolve();
    expect(mocks.portalFetch).not.toHaveBeenCalled();
    release?.();
    await pending;
    expect(mocks.portalFetch).toHaveBeenCalledOnce();
  });

  it("ends the session on a genuine 401 instead of presenting it as a capability denial", async () => {
    mocks.portalFetch.mockResolvedValue(new Response(null, { status: 401 }));
    await expect(apiGet("/training/operating/access")).rejects.toMatchObject({ message: "Your session has expired. Sign in again to continue.", status: 401 });
    expect(mocks.failure).toHaveBeenCalledWith("expired");
  });
});
