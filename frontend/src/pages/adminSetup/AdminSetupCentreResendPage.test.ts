import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const entry = readFileSync(new URL("../AdminSetupCentrePage.tsx", import.meta.url), "utf8");
const page = readFileSync(new URL("../AdminSetupCentreResendPage.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../../styles/admin-setup-resend.css", import.meta.url), "utf8");

describe("AMO Setup Centre supplied workflow adoption", () => {
  it("routes the setup page to the dedicated Resend-derived structure", () => {
    expect(entry).toContain('import AdminSetupCentreResendPage from "./AdminSetupCentreResendPage"');
    expect(entry).toContain("<AdminSetupCentreResendPage />");
    expect(entry).toContain("<AdminSetupWorkflowNavigator />");
    expect(page).toContain('className="setup-resend__rail"');
    expect(page).toContain('className="setup-resend__marker"');
    expect(page).toContain('className="setup-resend__context"');
  });

  it("copies the supplied workflow geometry instead of restyling the old dashboard", () => {
    expect(css).toContain("width: min(100%, 72rem)");
    expect(css).toContain("width: min(100%, 1100px)");
    expect(css).toContain("minmax(320px, 26rem)");
    expect(css).toContain("width: 21px");
    expect(css).toContain("border-radius: 30px");
    expect(css).toContain("min-height: 32px");
    expect(css).toContain("200ms ease-in-out");
  });

  it("renders only the selected step body while keeping the continuation stages compact", () => {
    expect(page).toContain("step.key === activeStep");
    expect(page).toContain("{active ? (");
    expect(css).toContain(".setup-resend__step:not(.is-active) .setup-resend__step-shell");
    expect(css).toContain("opacity: 0.52");
  });

  it("keeps the original setup services and tenant isolation wired", () => {
    expect(page).toContain("Promise.allSettled");
    expect(page).toContain("listBaseStations({ include_inactive: true })");
    expect(page).toContain("listSetupDepartments(true)");
    expect(page).toContain("getWorkforceHrDashboard(500)");
    expect(page).toContain("getPersonnelIdentityHealth()");
    expect(page).toContain("Failed data sources are cleared");
  });

  it("uses dismissible accessible notifications and visibly muted examples", () => {
    expect(page).toContain('role={tone === "danger" ? "alert" : "status"}');
    expect(page).toContain('aria-live={tone === "danger" ? "assertive" : "polite"}');
    expect(page).toContain('aria-label="Dismiss notification"');
    expect(css).toContain("--setup-placeholder: #52595b");
    expect(css).toContain("input::placeholder");
    expect(css).toContain("opacity: 1");
  });

  it("retains full base, department, workforce, asset and module actions", () => {
    expect(page).toContain("<BaseStationEditorDialog");
    expect(page).toContain("<DepartmentManager");
    expect(page).toContain("createBaseStation(payload)");
    expect(page).toContain("updateBaseStation(baseEditor.id, payload)");
    expect(page).toContain("uploadAmoLogo");
    expect(page).toContain("uploadAmoTemplate");
    expect(page).toContain("saveDownloadedFile(downloaded)");
  });
});
