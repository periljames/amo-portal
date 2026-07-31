import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiRequestMock } = vi.hoisted(() => ({ apiRequestMock: vi.fn() }));

vi.mock("./apiClient", () => ({
  apiRequest: apiRequestMock,
  qmsPath: (amoCode: string, suffix: string) => `/api/maintenance/${amoCode}/quality${suffix}`,
}));

import { getQmsDashboard, getQmsOperationalDashboard } from "./qmsDashboard";

describe("QMS dashboard services", () => {
  beforeEach(() => apiRequestMock.mockReset());

  it("keeps the bounded legacy counter endpoint for generic module pages", async () => {
    apiRequestMock.mockResolvedValue({ counters: {} });
    await getQmsDashboard("SAF");
    expect(apiRequestMock).toHaveBeenCalledWith(
      "/api/maintenance/SAF/quality/dashboard-lite",
      expect.objectContaining({ timeoutMs: 8_000, cacheTtlMs: 20_000 }),
    );
  });

  it("loads the server-ranked operational dashboard contract", async () => {
    const controller = new AbortController();
    apiRequestMock.mockResolvedValue({ contract: "qms-operational-dashboard.v2" });
    await getQmsOperationalDashboard("SAF", controller.signal);
    expect(apiRequestMock).toHaveBeenCalledWith(
      "/api/maintenance/SAF/quality/dashboard-v2",
      expect.objectContaining({ timeoutMs: 12_000, cacheTtlMs: 15_000, signal: controller.signal }),
    );
  });
});
