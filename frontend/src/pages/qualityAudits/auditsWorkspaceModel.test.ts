import { describe, expect, it } from "vitest";
import type { QMSAuditOut } from "../../services/qmsCore";
import {
  AUDITS_LIST_BOUND,
  buildAuditProgrammeLinkIndex,
  clampWorkspacePage,
  filterWorkspaceAudits,
  matchesWorkspaceSearch,
  matchesWorkspaceView,
  parseWorkspacePage,
  parseWorkspacePageSize,
  parseWorkspaceView,
  programmeLabelForAudit,
} from "./auditsWorkspaceModel";
import { auditNextAction } from "./auditNextAction";

function audit(overrides: Partial<QMSAuditOut> = {}): QMSAuditOut {
  return {
    id: "audit-1",
    domain: "AMO",
    kind: "INTERNAL",
    status: "PLANNED",
    audit_ref: "QAR/MO/26/001",
    title: "Procurement Audit",
    planned_start: "2026-08-25",
    planned_end: "2026-08-26",
    lead_auditor_user_id: "user-1",
    lead_auditor_name: "Lead One",
    updated_at: "2026-08-20T12:00:00Z",
    created_at: "2026-08-01T12:00:00Z",
    ...overrides,
  };
}

describe("auditsWorkspaceModel", () => {
  it("parses URL view, page, and page size with safe defaults", () => {
    expect(parseWorkspaceView("active")).toBe("active");
    expect(parseWorkspaceView("nope")).toBe("mine");
    expect(parseWorkspacePageSize("50")).toBe(50);
    expect(parseWorkspacePageSize("999")).toBe(25);
    expect(parseWorkspacePage("3")).toBe(3);
    expect(parseWorkspacePage("0")).toBe(1);
    expect(AUDITS_LIST_BOUND).toBe(250);
  });

  it("labels programme-linked audits from real schedule/requirement titles only", () => {
    const index = buildAuditProgrammeLinkIndex(
      [
        {
          id: "prog-1",
          programme_ref: "AP-2026-001",
          programme_series: "AP-2026",
          programme_year: 2026,
          revision_no: 1,
          title: "Annual programme",
          assurance_model: "HYBRID",
          continuous_monitoring_enabled: false,
          optimizer_version: "1",
          objectives: [],
          regulatory_basis: [],
          status: "ACTIVE",
          period_start: "2026-01-01",
          period_end: "2026-12-31",
          metrics: {
            planned_audit_count: 1,
            completed_audit_count: 0,
            deferred_audit_count: 0,
            cancelled_audit_count: 0,
            follow_up_audit_count: 0,
            scheduled_audit_count: 1,
          },
          items: [
            {
              id: "item-1",
              programme_id: "prog-1",
              universe_item_id: "u-1",
              audit_type: "INTERNAL",
              title: "Procurement Audit",
              scope: "Procurement",
              criteria: [],
              mandatory_surveillance: true,
              recurrence: "ANNUAL",
              state: "SCHEDULED",
              prioritization_basis: [],
            },
          ],
        },
      ],
      new Map([
        [
          "prog-1",
          [
            {
              programme_item_id: "item-1",
              state: "SCHEDULED",
              schedule_id: "sched-1",
              schedule_title: "Procurement Audit",
            },
          ],
        ],
      ]),
    );

    expect(programmeLabelForAudit(audit({ title: "Procurement Audit" }), index)).toBe(
      "AP-2026-001 · Procurement Audit",
    );
    expect(programmeLabelForAudit(audit({ title: "Ad-hoc hangar check" }), index)).toBe("Direct audit");
  });

  it("filters segmented views against live status and assignment", () => {
    const mine = audit({ lead_auditor_user_id: "me" });
    const other = audit({ id: "2", lead_auditor_user_id: "them", status: "IN_PROGRESS" });
    const closed = audit({ id: "3", status: "CLOSED", planned_start: "2026-01-01" });

    expect(matchesWorkspaceView(mine, "mine", "me")).toBe(true);
    expect(matchesWorkspaceView(other, "mine", "me")).toBe(false);
    expect(matchesWorkspaceView(other, "active", "me")).toBe(true);
    expect(matchesWorkspaceView(mine, "upcoming", "me")).toBe(true);
    expect(matchesWorkspaceView(closed, "completed", "me")).toBe(true);

    const rows = filterWorkspaceAudits([mine, other, closed], { view: "active", userId: "me" });
    expect(rows.map((row) => row.id)).toEqual(["2"]);
  });

  it("searches the loaded set and clamps pagination within that set", () => {
    const rows = [
      audit({ id: "a", audit_ref: "QAR/MO/26/001", title: "Procurement" }),
      audit({ id: "b", audit_ref: "QAR/MO/26/002", title: "Hangar", status: "IN_PROGRESS" }),
    ];
    expect(matchesWorkspaceSearch(rows[0], "procurement")).toBe(true);
    expect(filterWorkspaceAudits(rows, { view: "upcoming", search: "hangar" })).toHaveLength(0);
    expect(filterWorkspaceAudits(rows, { view: "active", search: "26/002" }).map((row) => row.id)).toEqual(["b"]);
    expect(clampWorkspacePage(9, 30, 25)).toBe(2);
    expect(clampWorkspacePage(1, 0, 25)).toBe(1);
  });

  it("keeps next-action navigation read-safe for in-progress audits", () => {
    expect(auditNextAction(audit({ status: "IN_PROGRESS", actual_start: "2026-08-25" }))).toEqual({
      label: "Continue audit",
      stage: "live",
    });
    expect(auditNextAction(audit({ status: "IN_PROGRESS", actual_start: null }))).toEqual({
      label: "Start fieldwork",
      stage: "live",
    });
  });
});
