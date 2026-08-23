import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = fileURLToPath(new URL(".", import.meta.url));
const read = (relative: string) => readFileSync(new URL(relative, `file://${here}/`), "utf8");

describe("roster spreadsheet interaction contract", () => {
  it("mounts the sheet gesture adapter and planner-only overrides", () => {
    const unified = read("./components/UnifiedRosterPlanner.tsx");
    expect(unified).toContain('import "./roster-spreadsheet-overrides.css"');
    expect(unified).toContain("<RosterSpreadsheetInteractions />");
  });

  it("supports pointer range selection plus Shift and Ctrl/Cmd extension", () => {
    const interactions = read("./components/RosterSpreadsheetInteractions.tsx");
    expect(interactions).toContain('addEventListener("pointerdown"');
    expect(interactions).toContain('addEventListener("pointermove"');
    expect(interactions).toContain("event.shiftKey || event.ctrlKey || event.metaKey");
    expect(interactions).toContain("dispatchCellClick(cell, true)");
    expect(interactions).toContain("MutationObserver");
  });

  it("removes personnel banding while preserving weekend and holiday date tinting", () => {
    const css = read("./components/roster-spreadsheet-overrides.css");
    expect(css).toContain(".wr-grid-row:nth-child(odd) > .wr-grid-person");
    expect(css).toContain(".wr-drop-cell:not(.is-weekend):not(.is-holiday)");
    expect(css).toContain(".wr-drop-cell.is-weekend");
    expect(css).toContain(".wr-drop-cell.is-holiday");
  });

  it("lets month columns expand to use available horizontal space", () => {
    const css = read("./components/roster-spreadsheet-overrides.css");
    expect(css).toContain("minmax(var(--wr-day-col), 1fr)");
    expect(css).toContain("width: max(100%");
  });
});
