import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const workspace = readFileSync(
  fileURLToPath(new URL("./QualityAuditsWorkspacePage.tsx", import.meta.url)),
  "utf8",
);
const listCss = readFileSync(
  fileURLToPath(new URL("./quality-audits-list-workspace.css", import.meta.url)),
  "utf8",
);

describe("audits workspace list page", () => {
  it("keeps view filters in page content (quality context hides shell header toolbar)", () => {
    expect(workspace).toContain('className="qa-audits-list__view-bar"');
    expect(workspace).toContain('label="Audit workspace view"');
    expect(workspace).not.toMatch(
      /QualityAuditsSectionLayout[\s\S]*?toolbar=\{[\s\S]*?ResponsiveSegmentedControl/,
    );
  });

  it("renders a clean pager total without corrupt placeholders", () => {
    expect(workspace).toContain("auditsQuery.data?.total ?? 0");
    expect(workspace).toContain("results · Page");
    expect(workspace).not.toMatch(/\u0085/);
    expect(workspace).not.toContain("Â·");
    expect(workspace).not.toContain("â€");
  });

  it("wraps audit identity titles instead of truncating with ellipsis", () => {
    expect(workspace).toContain("wrapText: true");
    expect(workspace).toContain("autoHeight: true");
    expect(listCss).toContain(".qa-audits-grid__identity strong");
    expect(listCss).toContain("white-space: normal");
    expect(listCss).not.toMatch(
      /\.qa-audits-grid__identity strong \{[^}]*text-overflow:\s*ellipsis/s,
    );
  });
});
