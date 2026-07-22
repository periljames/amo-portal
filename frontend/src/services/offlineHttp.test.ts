import { describe, expect, it } from "vitest";

import { isPortalCacheablePath } from "./offlineHttp";

describe("portal offline cache policy", () => {
  it("allows operational JSON endpoints", () => {
    expect(isPortalCacheablePath("/rostering/periods?from=2026-07-20&to=2026-07-26")).toBe(true);
    expect(isPortalCacheablePath("/workforce/people?active_only=true")).toBe(true);
    expect(isPortalCacheablePath("/qms/audits?page=1")).toBe(true);
  });

  it("excludes credentials, billing and downloadable artefacts", () => {
    expect(isPortalCacheablePath("/auth/me")).toBe(false);
    expect(isPortalCacheablePath("/accounts/admin/billing/invoices")).toBe(false);
    expect(isPortalCacheablePath("/rostering/reports/export?format=pdf")).toBe(false);
    expect(isPortalCacheablePath("/training/certificate.pdf")).toBe(false);
  });
});
