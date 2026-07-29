import { beforeEach, describe, expect, it, vi } from "vitest";

const { endSession } = vi.hoisted(() => ({ endSession: vi.fn() }));

vi.mock("./auth", () => ({
  authHeaders: () => ({ Authorization: "Bearer platform-token" }),
  endSession,
}));

vi.mock("./config", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));

import { platformConsoleApi } from "./platformConsole";

describe("platform console API", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    endSession.mockReset();
  });

  it("loads the live console bootstrap with platform authentication", async () => {
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

  it("encodes global search terms and result limits", async () => {
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

  it("invalidates the local session when console authorization expires", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 401 }));

    await expect(platformConsoleApi.bootstrap()).rejects.toThrow("Session expired. Please sign in again.");
    expect(endSession).toHaveBeenCalledWith("manual");
  });
});
