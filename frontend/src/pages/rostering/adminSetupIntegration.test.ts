import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const setupEntry = readFileSync(new URL("../AdminSetupCentrePage.tsx", import.meta.url), "utf8");
const setupPage = readFileSync(new URL("../AdminSetupCentreV2Page.tsx", import.meta.url), "utf8");
const baseEditor = readFileSync(new URL("../adminSetup/BaseStationEditorDialog.tsx", import.meta.url), "utf8");
const departmentManager = readFileSync(new URL("../adminSetup/DepartmentManager.tsx", import.meta.url), "utf8");
const setupRoute = readFileSync(new URL("../AdminAmoAssetsPage.tsx", import.meta.url), "utf8");
const overviewPage = readFileSync(new URL("../AdminOverviewPage.tsx", import.meta.url), "utf8");
const foundationsService = readFileSync(new URL("../../services/foundations.ts", import.meta.url), "utf8");
const departmentService = readFileSync(new URL("../../services/setupDepartments.ts", import.meta.url), "utf8");
const setupCss = readFileSync(new URL("../../styles/admin-setup-centre.css", import.meta.url), "utf8");
const locationCss = readFileSync(new URL("../../styles/admin-setup-location.css", import.meta.url), "utf8");
const setupShellCss = readFileSync(new URL("../../styles/admin-setup-shell.css", import.meta.url), "utf8");
const workforceDialogCss = readFileSync(new URL("../../styles/workforce-dialog-layer.css", import.meta.url), "utf8");
const rosteringCss = readFileSync(new URL("../../styles/rostering.css", import.meta.url), "utf8");
const performanceScript = readFileSync(new URL("../../../scripts/measure-rostering-load.mjs", import.meta.url), "utf8");
const releaseWorkflow = readFileSync(new URL("../../../../.github/workflows/release-candidate-recheck.yml", import.meta.url), "utf8");

describe("AMO administrator setup flow", () => {
  it("keeps the established route while using canonical setup services", () => {
    expect(setupRoute).toContain("AdminSetupCentrePage");
    expect(setupEntry).toContain("AdminSetupCentreV2Page");
    for (const contract of [
      "listBaseStations",
      "createBaseStation",
      "updateBaseStation",
      "listSetupDepartments",
      "listAdminUsers",
      "getWorkforceHrDashboard",
      "getPersonnelIdentityHealth",
      "getAmoAssets",
      "listAdminAssets",
    ]) {
      expect(setupPage).toContain(contract);
    }
  });

  it("routes setup actions to working module pages", () => {
    for (const route of [
      "/admin/users",
      "/rostering/settings?section=workforce",
      "/document-control/settings",
      "/admin/email-settings",
      "/admin/billing",
    ]) {
      expect(setupPage).toContain(route);
    }
    expect(overviewPage).toContain("/admin/amo-assets?tour=1");
    expect(overviewPage).not.toContain("/admin-users");
  });

  it("clears tenant state and rejects stale support-context responses", () => {
    expect(setupPage).toContain("const loadRequestRef = useRef(0)");
    expect(setupPage).toContain("const clearTenantState = useCallback");
    expect(setupPage).toContain("requestId !== loadRequestRef.current");
    expect(setupPage).toContain("setAssets(null)");
    expect(setupPage).toContain("setBases([])");
    expect(setupPage).toContain("setDepartments([])");
    expect(setupPage).toContain("setUsers([])");
  });

  it("switches REAL and DEMO support context with the selected AMO", () => {
    expect(setupPage).toContain("data_mode: selected.is_demo ? \"DEMO\" : \"REAL\"");
    expect(setupPage).toContain("active_amo_id: selected.id");
  });

  it("preserves the inactive-assets issue destination", () => {
    expect(setupPage).toContain("activeFilter === \"inactive\"");
    expect(setupPage).toContain("only_active: false");
    expect(setupPage).toContain("title=\"Inactive assets\"");
    expect(setupPage).toContain("Clear filter");
  });

  it("requires explicit, secure-context geolocation and never auto-prompts", () => {
    expect(baseEditor).toContain("window.isSecureContext");
    expect(baseEditor).toContain("navigator.geolocation.getCurrentPosition");
    expect(baseEditor).toContain("Use this device once");
    expect(baseEditor).toContain("Contribute independent sample");
    expect(baseEditor).not.toContain("navigator.geolocation.watchPosition");
    expect(baseEditor).not.toMatch(/useEffect\([^]*getCurrentPosition/);
  });

  it("uses aggregate location consensus without exposing raw peer observations", () => {
    for (const contract of [
      "contributeBaseLocation",
      "getBaseLocationConsensus",
      "approveBaseLocationConsensus",
      "clearBaseLocationObservations",
    ]) {
      expect(baseEditor).toContain(contract);
    }
    expect(baseEditor).toContain("Only aggregate quality and spread are shown");
    expect(foundationsService).not.toContain("listBaseLocationObservations");
    expect(setupPage).toContain("suspicious_location_review_enabled");
  });

  it("supports aerodrome suggestions with operator confirmation and manual fallback", () => {
    expect(baseEditor).toContain("searchAirportCatalog");
    expect(baseEditor).toContain("Type an ICAO/IATA code");
    expect(baseEditor).toContain("Confirm the current codes and coordinates");
    expect(baseEditor).toContain("Manual entry remains available");
    expect(foundationsService).toContain("/foundations/airport-catalog/search");
  });

  it("provides full tenant department CRUD without hidden seed actions", () => {
    expect(departmentService).toContain("/foundations/departments");
    expect(departmentService).toContain("createSetupDepartment");
    expect(departmentService).toContain("updateSetupDepartment");
    expect(departmentService).toContain("deleteSetupDepartment");
    expect(departmentManager).toContain("Add department");
    expect(departmentManager).toContain("Deactivate");
    expect(departmentManager).toContain("Delete");
    expect(departmentManager).toContain("assigned_user_count");
    expect(departmentManager).not.toContain("seedDefault");
  });

  it("keeps the Workforce editor visible without loading AMO setup CSS into Rostering", () => {
    expect(rosteringCss).toContain("workforce-dialog-layer.css");
    expect(rosteringCss).not.toContain("admin-setup-centre.css");
    expect(workforceDialogCss).toContain("body:has(.hr-decision)::before");
    expect(workforceDialogCss).toContain("z-index: 11000 !important");
    expect(workforceDialogCss).toContain(".hr-contract-editor .wr-actions--end");
  });

  it("removes the narrow setup constraint and keeps new controls responsive", () => {
    expect(setupCss).toContain(".admin-page.admin-amo-assets.setup-centre");
    expect(setupCss).toContain("max-width: none");
    expect(setupCss).toContain("repeat(auto-fit, minmax(340px, 1fr))");
    expect(setupShellCss).toContain(".app-shell__content:has(.admin-amo-assets.setup-centre)");
    expect(setupShellCss).toContain("max-width: none");
    expect(locationCss).toContain(".setup-dialog--wide");
    expect(locationCss).toContain(".setup-department-table");
    expect(locationCss).toContain("@media (max-width: 760px)");
  });

  it("verifies server assets and Chromium cache hits without weakening budgets", () => {
    expect(releaseWorkflow).toContain("find dist -maxdepth 2");
    expect(releaseWorkflow).toContain("for attempt in $(seq 1 10)");
    expect(releaseWorkflow).toContain("Asset not available");
    expect(performanceScript).toContain("fetchWithRetry");
    expect(performanceScript).toContain("cacheMode: \"force-cache\"");
    expect(performanceScript).toContain("Network.requestServedFromCache");
    expect(performanceScript).toContain("missingCacheHits");
    expect(performanceScript).not.toContain("offline: true");
    expect(performanceScript).toContain("warmRouteAssetsMs: 5_000");
  });
});
