import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installPortalFetchErrorBridge } from "./portalFetchErrorBridge";
import { getToken, handleAuthFailure, recoverSessionAfterUnauthorized } from "./auth";

vi.mock("./auth", () => ({
  ensureAuthenticatedRequestAllowed: () => true,
  getToken: vi.fn(() => "old-token"), getTokenSecondsRemaining: () => 3600,
  hasRecoverableSession: () => true, handleAuthFailure: vi.fn(),
  recoverSessionAfterUnauthorized: vi.fn(),
}));
vi.mock("./portalConnectivity", () => ({
  markPortalSessionExpired: vi.fn(), notePortalNetworkFailure: vi.fn(), notePortalResponse: vi.fn(),
}));
vi.mock("./portalError", () => ({ reportPortalError: vi.fn(), reportUploadError: vi.fn() }));
vi.mock("./config", () => ({ getApiBaseUrl: () => "http://portal.test" }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getToken).mockReturnValue("old-token");
  vi.stubGlobal("document", new EventTarget());
});
afterEach(() => vi.unstubAllGlobals());

function install(fetch: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("window", Object.assign(new EventTarget(), {
    fetch, location: { origin: "http://portal.test" },
  }));
  installPortalFetchErrorBridge();
}

describe("protected request recovery", () => {
  it("does not log out when a 401 is followed by deferred recovery", async () => {
    install(vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
    vi.mocked(recoverSessionAfterUnauthorized).mockResolvedValue(null);
    const response = await window.fetch("http://portal.test/auth/me", {
      headers: { Authorization: "Bearer old-token" },
    });
    expect(response.status).toBe(503);
    expect(handleAuthFailure).not.toHaveBeenCalled();
  });

  it("retries stale 401s using a token that was refreshed during the request", async () => {
    const fetch = vi.fn().mockImplementationOnce(() => {
      vi.mocked(getToken).mockReturnValue("new-token");
      return Promise.resolve(new Response(null, { status: 401 }));
    }).mockResolvedValue(new Response(null, { status: 200 }));
    install(fetch);
    const response = await window.fetch("http://portal.test/auth/me", {
      headers: { Authorization: "Bearer old-token" },
    });
    expect(response.status).toBe(200);
    expect(recoverSessionAfterUnauthorized).not.toHaveBeenCalled();
    expect(new Headers(fetch.mock.calls[1][1].headers).get("Authorization")).toBe("Bearer new-token");
  });

  it("still ends the session if the newer token is also rejected", async () => {
    vi.mocked(getToken).mockReturnValue("new-token");
    install(vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
    const response = await window.fetch("http://portal.test/auth/me", {
      headers: { Authorization: "Bearer old-token" },
    });
    expect(response.status).toBe(401);
    expect(handleAuthFailure).toHaveBeenCalledOnce();
  });
});
