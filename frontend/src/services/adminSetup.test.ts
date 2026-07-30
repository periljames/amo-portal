import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const setupPage = readFileSync(new URL("../pages/AdminAmoAssetsPage.tsx", import.meta.url), "utf8");
const overviewPage = readFileSync(new URL("../pages/AdminOverviewPage.tsx", import.meta.url), "utf8");
const setupCss = readFileSync(new URL("../styles/admin-setup-centre.css", import.meta.url), "utf8");
const setupShellCss = readFileSync(new URL("../styles/admin-setup-shell.css", import.meta.url), "utf8");
const rosteringCss = readFileSync(new URL("../styles/rostering.css", import.meta.url), "utf8");

describe("AMO administrator setup flow", () => {
  it("uses canonical backend services for setup readiness and editing", () => {
    for (const contract of [
      "listBaseStations",
      "createBaseStation",
      "updateBaseStation",
      "listAdminDepartments",
      "listAdminUsers",
      "getWorkforceHrDashboard",
      "getPersonnelIdentityHealth",
      "getAmoAssets",
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

  it("keeps the Workforce editor visible above the portal shell", () => {
    expect(rosteringCss).toContain("admin-setup-centre.css");
    expect(setupCss).toContain("body:has(.hr-decision)::before");
    expect(setupCss).toContain("z-index: 11000 !important");
    expect(setupCss).toContain(".hr-contract-editor .wr-actions--end");
  });

  it("removes the narrow admin assets constraint at page and shell level", () => {
    expect(setupCss).toContain(".admin-page.admin-amo-assets.setup-centre");
    expect(setupCss).toContain("max-width: none");
    expect(setupCss).toContain("repeat(auto-fit, minmax(340px, 1fr))");
    expect(setupShellCss).toContain(".app-shell__content:has(.admin-amo-assets.setup-centre)");
    expect(setupShellCss).toContain("max-width: none");
  });
});
