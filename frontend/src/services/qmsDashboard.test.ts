import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiRequestMock } = vi.hoisted(() => ({ apiRequestMock: vi.fn() }));

vi.mock("./apiClient", () => ({
  apiRequest: apiRequestMock,
  qmsPath: (amoCode: string, suffix: string) => `/api/maintenance/${amoCode}/quality${suffix}`,
}));

import { getQmsDashboard, getQmsOperationalDashboard } from "./qmsDashboard";

describe("QMS dashboard services", () => {
  beforeEach(() => apiRequestMock.mockReset());

  it("loads the bounded summary with tenant-persisted slow-network fallback", async () => {
    apiRequestMock.mockResolvedValue({ counters: {} });
    await getQmsDashboard("SAF");
    expect(apiRequestMock).toHaveBeenCalledWith(
      "/api/maintenance/SAF/quality/dashboard-lite",
      expect.objectContaining({
        timeoutMs: 10_000,
        cacheTtlMs: 30_000,
        persistCache: true,
        staleWhileOfflineMs: 30 * 60_000,
      }),
    );
  });

  it("loads the server-ranked operational contract without dropping cancellation", async () => {
    const controller = new AbortController();
    apiRequestMock.mockResolvedValue({ contract: "qms-operational-dashboard.v2" });
    await getQmsOperationalDashboard("SAF", controller.signal);
    expect(apiRequestMock).toHaveBeenCalledWith(
      "/api/maintenance/SAF/quality/dashboard-v2",
      expect.objectContaining({
        timeoutMs: 15_000,
        cacheTtlMs: 20_000,
        persistCache: true,
        staleWhileOfflineMs: 30 * 60_000,
        signal: controller.signal,
      }),
    );
  });
});
