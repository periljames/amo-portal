import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiRequestMock } = vi.hoisted(() => ({ apiRequestMock: vi.fn() }));

vi.mock("./apiClient", () => ({ apiRequest: apiRequestMock }));

import { getDepartmentHome } from "./departmentHome";

describe("department home service", () => {
  beforeEach(() => apiRequestMock.mockReset());

  it("encodes tenant and department into the authenticated home endpoint", async () => {
    const controller = new AbortController();
    apiRequestMock.mockResolvedValue({ contract: "department-home.v1" });

    await getDepartmentHome("AMO 001", "document-control", controller.signal);

    expect(apiRequestMock).toHaveBeenCalledWith(
      "/auth/home/AMO%20001/document-control",
      expect.objectContaining({
        timeoutMs: 12_000,
        cacheTtlMs: 20_000,
        staleWhileOfflineMs: 20 * 60_000,
        persistCache: true,
        signal: controller.signal,
      }),
    );
  });

  it("does not construct a cross-tenant URL from an unescaped tenant value", async () => {
    apiRequestMock.mockResolvedValue({ contract: "department-home.v1" });

    await getDepartmentHome("tenant-a/../../tenant-b", "planning");

    const [path] = apiRequestMock.mock.calls[0];
    expect(path).toBe("/auth/home/tenant-a%2F..%2F..%2Ftenant-b/planning");
    expect(path).not.toContain("/tenant-b/planning");
  });
});
