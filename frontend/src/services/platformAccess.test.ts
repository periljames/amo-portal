import { beforeEach, describe, expect, it, vi } from "vitest";

const { cacheCurrentUser, handleAuthFailure } = vi.hoisted(() => ({
  cacheCurrentUser: vi.fn(),
  handleAuthFailure: vi.fn(),
}));

vi.mock("./auth", () => ({
  authHeaders: (extra?: HeadersInit) => new Headers({
    Authorization: "Bearer platform-token",
    ...(extra ? Object.fromEntries(new Headers(extra).entries()) : {}),
  }),
  cacheCurrentUser,
  handleAuthFailure,
}));

vi.mock("./config", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));

import { verifyCurrentPlatformUser } from "./platformAccess";

describe("platform access verification", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    cacheCurrentUser.mockReset();
    handleAuthFailure.mockReset();
  });

  it("caches an authoritative active platform user", async () => {
    const user = { id: "root", email: "root@example.test", is_superuser: true };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(user), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(verifyCurrentPlatformUser()).resolves.toEqual(user);
    expect(cacheCurrentUser).toHaveBeenCalledWith(user);
    expect(handleAuthFailure).not.toHaveBeenCalled();

    const [, init] = fetchMock.mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Bearer platform-token");
    expect(headers.get("Accept")).toBe("application/json");
  });

  it("clears local authentication when the server rejects an inactive platform account", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Inactive user account" }), {
        status: 400,
        headers: { "content-type": "application/json" },
      }),
    );

    const pending = verifyCurrentPlatformUser();
    await expect(pending).rejects.toMatchObject({
      name: "PlatformAccessVerificationError",
      status: 400,
      message: "Inactive user account",
    });
    expect(handleAuthFailure).toHaveBeenCalledWith("platform-access-rejected:400");
    expect(cacheCurrentUser).not.toHaveBeenCalled();
  });

  it("does not destroy a valid cached session for a transient server failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Verification service unavailable" }), {
        status: 503,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(verifyCurrentPlatformUser()).rejects.toMatchObject({
      name: "PlatformAccessVerificationError",
      status: 503,
    });
    expect(handleAuthFailure).not.toHaveBeenCalled();
  });
});
