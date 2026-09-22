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

  it("centres the audit-area title and puts role-styled initials in its scheduled slot", () => {
    expect(matrix).not.toContain("Lead auditor ·");
    expect(matrix).toContain("<strong>{data.area.display_label}</strong>");
    expect(matrix).not.toContain("planned audits`");
    expect(matrix).not.toContain("{subtitle ? <small>{subtitle}</small> : null}");
    expect(matrix).toContain("buildProgrammeMatrixRows");
    expect(matrix).toContain("primaryProgrammeItem");
    expect(matrix).toContain("slotsForMonth");
    expect(matrix).toContain('className="qms-programme-matrix__assignees"');
    expect(matrix).toContain("<AuditLeadInitials");
    expect(matrix).toContain("<AuditTeamRestInitials");
    expect(matrix).toContain('assignment.role !== "lead"');
    expect(matrix).toContain("auditorInitials.get(leadId)");
    expect(matrix).not.toContain("Available to plan");
    expect(matrix).not.toContain("human(data.area.entity_type)");
    expect(page).toContain("auditorNames={auditorNames}");
  });

  it("keeps the annual planner compact and internally scrollable", () => {
    expect(matrix).toContain('type MatrixView = "all" | "programme"');
    expect(matrix).toContain("rowHeight={64}");
    expect(matrix).toContain("wrapText: true");
    expect(matrix).toContain("autoHeight: true");
    expect(matrix).toContain(
      "In programme <span>{programmeRows.length}</span>",
    );
    expect(matrix).not.toContain('domLayout="autoHeight"');
    expect(matrix).not.toContain("<small>Plan</small>");
  });

  it("keeps one matrix row per audit area across planned months", () => {
    expect(matrix).toContain("buildProgrammeMatrixRows");
    expect(matrix).not.toContain("id: `item-${item.id}`");
    expect(matrix).toContain("slotsForMonth(");
  });

  it("uses compact aircraft and date labels without recurrence tags", () => {
    expect(matrix).toContain("slotLabel(slot.item, slot.entry.label)");
    expect(matrix).toContain("programmeMatrixSlotLabel");
    expect(matrix).toContain("resolveAircraftRegistration");
    expect(matrix).toContain("slotTitle(");
    expect(matrix).not.toContain("entry.detail");
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

  it("uses static audit-area columns and current grid context", () => {
    expect(page).toContain("const AUDIT_AREA_COLUMNS:");
    expect(page).toContain("columnDefs={AUDIT_AREA_COLUMNS}");
    expect(page).toContain("context={universeGridContext}");
    expect(page).not.toContain("columnDefs={universeColumns}");
  });

  it("opens every audit in an area from Info and keeps delete in plan dialogs", () => {
    expect(matrix).toContain("onViewArea");
    expect(matrix).toContain("actions.onViewArea(areaItems, data.area.display_label)");
    expect(matrix).toContain('className={`qms-programme-matrix__chip');
    expect(matrix).not.toContain('aria-label={`Remove ${primary.title}`}');
    expect(page).toContain("areaAuditsFocus");
    expect(page).toContain("openRemoveAudit");
    expect(page).toContain("Delete audit");
    expect(page).toContain("programmeItemIdentity");
    expect(page).toContain("groupAreaAuditsByMonth");
    expect(page).toContain('className="qms-programme-area-month"');
    expect(page).toContain("qms-programme-area-tile__actions");
    expect(page).not.toContain("<Info size={14} /> Details");
  });

  it("allows assign-later lead and auditor fallback for planned audits", () => {
    expect(page).toContain("programmeLeadAuditorOptions");
    expect(page).toContain("Assign later");
    expect(page).toContain("leadOptionsAreFallbackAuditors");
    expect(page).not.toContain(
      "!itemForm.lead_auditor_user_id))",
    );
    expect(page).not.toContain(
      "!calendarMonthForm.lead_auditor_user_id) ||",
    );
    expect(page).not.toContain(
      "required={itemForm.recurrence === \"FIXED_DATES\"}\n                value={itemForm.lead_auditor_user_id}",
    );
    expect(page).not.toContain(
      "required={calendarMonthForm.dates.length > 0}\n                  value={calendarMonthForm.lead_auditor_user_id}",
    );
  });

  it("defaults next-year create to carry forward prior-year audits", () => {
    expect(page).toContain("priorYearQuery");
    expect(page).toContain("defaultCopyPreviousYear");
    expect(page).toContain("emptyYearCreateLabel");
    expect(page).toContain("carryForwardResultToast");
    expect(page).toContain("copyPreviousYear: canCarryForwardDefaultKind");
    expect(page).toContain("defaultRotateAuditors");
    expect(page).toContain("rotate_auditors");
    expect(page).toContain("Rotate auditors");
    expect(page).toContain("HistoryTextarea");
    expect(page).toContain("useTextFieldHistory");
    expect(page).toContain("fieldHistoryAreaFromEntity");
    expect(page).toContain("purposeHistoryAdd");
  });
});
