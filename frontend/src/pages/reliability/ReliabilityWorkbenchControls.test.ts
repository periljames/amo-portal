import { describe, expect, it } from "vitest";

import { spreadsheetSafeText } from "./ReliabilityWorkbenchUtils";

describe("Reliability spreadsheet workbench safety", () => {
  it("neutralizes spreadsheet formula prefixes in exported or copied text", () => {
    expect(spreadsheetSafeText("=HYPERLINK(\"https://example.invalid\")")).toBe("'=HYPERLINK(\"https://example.invalid\")");
    expect(spreadsheetSafeText("+SUM(A1:A2)")).toBe("'+SUM(A1:A2)");
    expect(spreadsheetSafeText("-1+2")).toBe("'-1+2");
    expect(spreadsheetSafeText("@cmd")).toBe("'@cmd");
    expect(spreadsheetSafeText("  =1+1")).toBe("'  =1+1");
  });

  it("leaves ordinary Reliability evidence unchanged", () => {
    expect(spreadsheetSafeText("5Y-SLK")).toBe("5Y-SLK");
    expect(spreadsheetSafeText("ATA 32")).toBe("ATA 32");
    expect(spreadsheetSafeText(12.375)).toBe("12.375");
    expect(spreadsheetSafeText(null)).toBe("");
  });
});
