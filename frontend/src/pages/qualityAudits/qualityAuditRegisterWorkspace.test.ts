import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { isEffectivenessResponseRoute } from "../../components/QMS/qmsEffectivenessRoute";

const register = readFileSync(fileURLToPath(new URL("./QualityAuditRegisterPage.tsx", import.meta.url)), "utf8");
const enhancements = readFileSync(fileURLToPath(new URL("../../components/QMS/QualityEffectivenessResponseHost.tsx", import.meta.url)), "utf8");
const workspaceCss = readFileSync(fileURLToPath(new URL("./quality-audits-workspace.css", import.meta.url)), "utf8");

describe("findings and corrective-action workspace", () => {
  it("renders explicit operational states instead of an empty grid shell", () => {
    expect(register).toContain("No findings or corrective actions yet");
    expect(register).toContain("registerQuery.isLoading");
    expect(register).toContain("registerQuery.isError");
    expect(register).toContain(") : rows.length ? (");
    expect(register).toContain('<Pagination label="Findings"');
  });

  it("keeps the finding and corrective action in one visible lifecycle", () => {
    expect(register).toContain("Observations stay as findings");
    expect(register).toContain("About this register");
    expect(register).toContain("Follow-up settings");
    expect(register).toContain("Show filters");
    expect(register).toContain("qa-register-grid-page__filter-pan");
    expect(register).toContain("qa-register-grid-page__icon-btn");
    expect(register).not.toContain("Matching this view");
    expect(register).not.toContain(">Search</button>");
    expect(register).toContain('headerName: "Corrective action"');
    expect(register).toContain('headerName: "Stage"');
    expect(register).toContain("findingNextAction");
  });

  it("does not float effectiveness controls over register or programme pages", () => {
    expect(enhancements).toContain("isEffectivenessResponseRoute");
    expect(isEffectivenessResponseRoute("/maintenance/test/quality/audits/register", "")).toBe(false);
    expect(isEffectivenessResponseRoute("/maintenance/test/quality/findings/abc", "")).toBe(false);
    expect(isEffectivenessResponseRoute("/maintenance/test/quality/cars/abc", "")).toBe(false);
    expect(isEffectivenessResponseRoute("/maintenance/test/quality/assurance/cases", "")).toBe(true);
    expect(isEffectivenessResponseRoute("/maintenance/test/quality/audits/register", "?workspace=assurance")).toBe(true);
    expect(isEffectivenessResponseRoute("/maintenance/test/quality/cars/register", "")).toBe(false);
  });

  it("keeps Assurance pages full-height with efficient main scrolling", () => {
    expect(workspaceCss).not.toContain("--qa-assurance-chrome-offset");
    expect(workspaceCss).toContain(".qa-workspace-main > :not(.qa-workspace-page-title)");
    expect(workspaceCss).toContain(".qa-workspace-main > .qa-workspace-page-title { flex: 0 0 auto; }");
    expect(workspaceCss).toContain("min-height: 0");
    expect(workspaceCss).toContain("overscroll-behavior: contain");
  });
});
