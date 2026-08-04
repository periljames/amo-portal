import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const setupEntry = readFileSync(new URL("../AdminSetupCentrePage.tsx", import.meta.url), "utf8");
const setupCss = readFileSync(new URL("../../styles/admin-setup-workflow.css", import.meta.url), "utf8");
const inlineAlert = readFileSync(new URL("../../components/UI/Admin/InlineAlert.tsx", import.meta.url), "utf8");

describe("AMO Setup Centre focused workflow presentation", () => {
  it("loads the dedicated workflow layer after the legacy location styles", () => {
    expect(setupEntry).toContain('import "../styles/admin-setup-location.css"');
    expect(setupEntry).toContain('import "../styles/admin-setup-workflow.css"');
    expect(setupEntry.indexOf("admin-setup-workflow.css"))
      .toBeGreaterThan(setupEntry.indexOf("admin-setup-location.css"));
  });

  it("uses a compact desktop canvas and responsive two-column editor", () => {
    expect(setupCss).toContain("grid-template-columns: minmax(0, 1fr) minmax(360px, 520px)");
    expect(setupCss).toContain("width: min(100%, 1480px)");
    expect(setupCss).toContain("grid-template-columns: minmax(0, 1.05fr) minmax(330px, 0.95fr)");
    expect(setupCss).toContain("max-width: 1120px");
    expect(setupCss).toContain("@media (max-width: 760px)");
    expect(setupCss).toContain("min-height: 100dvh");
  });

  it("shows setup feedback as an accessible high-contrast notification", () => {
    expect(setupCss).toContain("> .admin-inline-alert");
    expect(setupCss).toContain("position: fixed");
    expect(setupCss).toContain("z-index: 13000");
    expect(setupCss).toContain("background: #8f1d1d");
    expect(inlineAlert).toContain('role={urgent ? "alert" : "status"}');
    expect(inlineAlert).toContain('aria-live={urgent ? "assertive" : "polite"}');
    expect(inlineAlert).toContain('aria-atomic="true"');
  });

  it("keeps example text visibly subordinate to entered values", () => {
    expect(setupCss).toContain("input::placeholder");
    expect(setupCss).toContain("textarea::placeholder");
    expect(setupCss).toContain("opacity: 0.42");
  });

  it("renders readiness as one restrained status list instead of nested hero cards", () => {
    expect(setupCss).toContain("border-bottom: 1px solid var(--setup-border)");
    expect(setupCss).toContain("border-radius: 0");
    expect(setupCss).toContain("min-height: 56px");
    expect(setupCss).toContain("box-shadow: none");
  });
});
