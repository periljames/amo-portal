import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const matrix = readFileSync(
  fileURLToPath(new URL("./QmsAuditProgrammeMatrix.tsx", import.meta.url)),
  "utf8",
);
const page = readFileSync(
  fileURLToPath(new URL("./QmsAuditProgrammePageV2.tsx", import.meta.url)),
  "utf8",
);

describe("audit programme grid lifecycle", () => {
  it("keeps the 12-month column graph stable while query state rerenders", () => {
    expect(matrix).toContain('colId: "audit-area"');
    expect(matrix).toContain("colId: `month-${month}`");
    expect(matrix).toContain(
      "key={`${programme.id}:${programme.programme_year}`}",
    );
    expect(matrix).toContain("defaultColDef={MATRIX_DEFAULT_COL_DEF}");
    expect(matrix).toContain("actionsRef.current = {");
  });

  it("keeps the annual planner compact and internally scrollable", () => {
    expect(matrix).toContain('type MatrixView = "all" | "programme"');
    expect(matrix).toContain("rowHeight={54}");
    expect(matrix).toContain(
      "In programme <span>{programmeRows.length}</span>",
    );
    expect(matrix).not.toContain('domLayout="autoHeight"');
    expect(matrix).not.toContain("<small>Plan</small>");
  });

  it("centres the audit-area title and puts role-styled initials in its scheduled slot", () => {
    expect(matrix).not.toContain("Lead auditor ·");
    expect(matrix).toContain("<strong>{data.area.display_label}</strong>");
    expect(matrix).toContain(
      "{data.item ? <small>{data.item.title}</small> : null}",
    );
    expect(matrix).toContain('className="qms-programme-matrix__assignees"');
    expect(matrix).toContain("<AuditTeamInitials");
    expect(matrix).toContain('assignment.role === "lead"');
    expect(matrix).toContain('assignment.role === "observer"');
    expect(matrix).toContain("auditorInitials.get(assignment.id)");
    expect(matrix).not.toContain("Available to plan");
    expect(matrix).not.toContain("human(data.area.entity_type)");
    expect(page).toContain("auditorNames={auditorNames}");
  });

  it("switches between internal, external, and combined programmes", () => {
    expect(matrix).toContain(
      'export type AuditKindView = "INTERNAL" | "EXTERNAL" | "BOTH"',
    );
    expect(matrix).toContain('["INTERNAL", "EXTERNAL", "BOTH"]');
    expect(matrix).toContain("onAuditKindViewChange(kind)");
    expect(page).toContain("matrixPortfolioQuery");
    expect(page).toContain("items={matrixItems}");
    expect(page).toContain("scheduleLinks={matrixScheduleLinks}");
  });

  it("shows actionable auditor collisions in the scheduled slot", () => {
    expect(matrix).toContain("findAuditorScheduleCollisions");
    expect(matrix).toContain('className="qms-programme-matrix__collision"');
    expect(matrix).toContain("Assign another lead");
    expect(matrix).toContain("Reschedule audit");
  });

  it("uses compact aircraft and date labels without recurrence tags", () => {
    expect(matrix).toContain("slotLabel(data.item, entry.label)");
    expect(matrix).toContain("aircraftRegistrationSuffix");
    expect(matrix).toContain("ordinalDayLabel");
    expect(matrix).not.toContain("entry.detail");
  });

  it("uses static audit-area columns and current grid context", () => {
    expect(page).toContain("const AUDIT_AREA_COLUMNS:");
    expect(page).toContain("columnDefs={AUDIT_AREA_COLUMNS}");
    expect(page).toContain("context={universeGridContext}");
    expect(page).not.toContain("columnDefs={universeColumns}");
  });
});
