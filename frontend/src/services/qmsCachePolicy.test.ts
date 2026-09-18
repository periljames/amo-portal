import { describe, expect, it } from "vitest";
import { isQmsLiveAuthority, withoutQmsAuthority } from "./qmsCachePolicy";
import { isPortalCacheablePath } from "./offlineHttp";
import { collectQmsPrecacheUrls } from "../../scripts/qmsPrecacheGraph";

describe("QMS offline cache boundaries", () => {
  it("keeps operational records cacheable but rechecks authority live", () => {
    expect(isPortalCacheablePath("/api/maintenance/t/quality/audits/a1")).toBe(true);
    expect(isPortalCacheablePath("/api/maintenance/t/quality/audits/a1/assignment-eligibility?user_id=u1")).toBe(false);
    expect(isQmsLiveAuthority("qms-audit-assignment-eligibility:t:a1:LEAD_AUDITOR:u1")).toBe(true);
  });
  it("removes authority from previously persisted snapshots without discarding drafts", () => {
    const mutations = [{ mutationKey: ["qms-draft"] }];
    const cached = { clientState: { mutations, queries: [
      { queryKey: ["qms", "audit-occurrence", "t", "a1"] },
      { queryKey: ["qms-audit-assignment-eligibility", "t", "a1"] },
    ] } };
    const restored = withoutQmsAuthority(cached)!;
    expect(restored.clientState.queries).toHaveLength(1);
    expect(restored.clientState.mutations).toBe(mutations);
    expect(cached.clientState.queries).toHaveLength(2);
  });
  it("precaches lazy Quality pages and their shared dependencies, excluding other modules", () => {
    const urls = collectQmsPrecacheUrls({
      "index.html": { file: "assets/main.js" },
      "src/pages/qms/QmsCanonicalPage.tsx": { file: "assets/qms.js", imports: ["shared"], css: ["assets/qms.css"] },
      "src/features/qms/auditSession/AuditSetupWorkspace.tsx": { file: "assets/setup.js", imports: ["shared"] },
      shared: { file: "assets/shared.js", imports: ["cycle"] },
      cycle: { file: "assets/cycle.js", imports: ["shared"] },
      "src/pages/PayrollPage.tsx": { file: "assets/payroll.js" },
    });
    expect(urls).toEqual(["/assets/cycle.js", "/assets/qms.css", "/assets/qms.js", "/assets/setup.js", "/assets/shared.js"]);
  });
});
