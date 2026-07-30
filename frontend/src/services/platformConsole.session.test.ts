import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  extendSessionIfNeeded,
  handleAuthFailure,
  markSessionActivity,
} = vi.hoisted(() => ({
  extendSessionIfNeeded: vi.fn(),
  handleAuthFailure: vi.fn(),
  markSessionActivity: vi.fn(),
}));

vi.mock("./auth", () => ({
  authHeaders: () => new Headers({ Authorization: "Bearer live-platform-token" }),
  extendSessionIfNeeded,
  handleAuthFailure,
  markSessionActivity,
}));

vi.mock("./config", () => ({
  getApiBaseUrl: () => "https://portal.example.test",
}));

import { platformConsoleApi } from "./platformConsole";

describe("platform console session transport", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    extendSessionIfNeeded.mockReset();
    extendSessionIfNeeded.mockReturnValue(null);
    handleAuthFailure.mockReset();
    markSessionActivity.mockReset();
  });

  it("preserves a Bearer token supplied through the Headers API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ generated_at: "2026-07-30T00:00:00Z" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await platformConsoleApi.bootstrap();

    const [, init] = fetchMock.mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Bearer live-platform-token");
    expect(headers.get("Accept")).toBe("application/json");
  });

  it("waits for a near-expiry session extension before dispatching the request", async () => {
    let releaseExtension: (() => void) | undefined;
    extendSessionIfNeeded.mockReturnValue(new Promise((resolve) => {
      releaseExtension = () => resolve(null);
    }));
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const pending = platformConsoleApi.search("tenant");
    await Promise.resolve();
    expect(fetchMock).not.toHaveBeenCalled();

    releaseExtension?.();
    await pending;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not post a second logout when the server rejects the token", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 401 }));

    await expect(platformConsoleApi.bootstrap()).rejects.toThrow("Session expired. Please sign in again.");
    expect(handleAuthFailure).toHaveBeenCalledWith("platform-console-unauthorized");
  });
});
