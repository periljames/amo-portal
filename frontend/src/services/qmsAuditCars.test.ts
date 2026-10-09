import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./apiClient";
import { listAuditCorrectiveActions } from "./qmsAuditCars";

vi.mock("./apiClient", () => ({
  apiRequest: vi.fn(), qmsPath: (amo: string, suffix: string) => `/quality/${amo}${suffix}`,
}));

const request = vi.mocked(apiRequest);
const car = (id: string, auditId = "audit-1") => ({ id, audit_id: auditId, car_number: id, title: "Finding response", status: "OPEN", priority: "MEDIUM" });

describe("complete audit CAR collection", () => {
  beforeEach(() => request.mockReset());

  it("includes corrective actions beyond the first page", async () => {
    request.mockResolvedValueOnce({ items: Array.from({ length: 200 }, (_, index) => car(`car-${index}`)), total: 201, limit: 200, offset: 0 });
    request.mockResolvedValueOnce({ items: [car("last-car")], total: 201, limit: 200, offset: 200 });
    const result = await listAuditCorrectiveActions("tenant-a", "audit-1");
    expect(result.items).toHaveLength(201);
    expect(result.items.at(-1)?.id).toBe("last-car");
  });

  it("rejects an incomplete register instead of showing a misleading closure queue", async () => {
    request.mockResolvedValueOnce({ items: [], total: 1, limit: 200, offset: 0 });
    await expect(listAuditCorrectiveActions("tenant-a", "audit-1")).rejects.toThrow("full corrective-action register");
  });

  it("rejects a CAR from another occurrence", async () => {
    request.mockResolvedValueOnce({ items: [car("other-car", "other-audit")], total: 1, limit: 200, offset: 0 });
    await expect(listAuditCorrectiveActions("tenant-a", "audit-1")).rejects.toThrow("could not be verified for this audit");
  });
});
