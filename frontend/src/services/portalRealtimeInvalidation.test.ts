import { describe, expect, it } from "vitest";
import { queryMatchesRealtimeMarkers, realtimeQueryMarkers } from "./portalRealtimeInvalidation";

describe("cross-device event invalidation", () => {
  it.each([
    ["qms.audit", "qms-audit-list"], ["training.session", "training-person"],
    ["rostering.assignment", "rostering"], ["workforce.attendance", "workforce"],
    ["work.task", "work-orders"], ["fleet.aircraft", "aircraft"],
    ["document.revision", "documents"], ["technical_records.record", "technical-records"],
    ["reliability.engine", "reliability"], ["inventory.part", "inventory"],
    ["procurement.order", "procurement"], ["finance.invoice", "finance"],
    ["accounts.user", "users"],
  ])("refreshes %s data on another connected device", (entityType, key) => {
    expect(queryMatchesRealtimeMarkers([key, "amo"], realtimeQueryMarkers({ type: `${entityType}.updated`, entityType }))).toBe(true);
  });
  it("does not refresh unrelated modules or match car inside aircraft", () => {
    const markers = realtimeQueryMarkers({ type: "fleet.aircraft.updated", entityType: "aircraft" });
    expect(queryMatchesRealtimeMarkers(["qms-audit", "amo"], markers)).toBe(false);
    expect(realtimeQueryMarkers({ type: "presence.typing", entityType: "presence" })).toEqual([]);
  });
  it.each(["qms-current-dms-checklists", "qms-canonical-document-control-documents", "qms-audit-preparation-readiness", "checklist-evidence-candidates"])("refreshes dependent %s when DMS approvals change", (key) => {
    const markers = realtimeQueryMarkers({ type: "doc_control.revision_issued", entityType: "DocumentWorkflow", metadata: { module: "doc_control" } });
    expect(queryMatchesRealtimeMarkers([key, "amo", "audit-1"], markers)).toBe(true);
    expect(queryMatchesRealtimeMarkers(["qms", "live-audit-checklist", "audit-1"], markers)).toBe(false);
    expect(queryMatchesRealtimeMarkers(["fleet", "amo"], markers)).toBe(false);
  });
  it("recognizes actual model entity names without guessing substrings", () => {
    expect(realtimeQueryMarkers({ type: "changed", entityType: "QMSAuditChecklistItem" })).toContain("qms");
    expect(realtimeQueryMarkers({ type: "doc_control.changed", entityType: "workflow" })).toContain("documents");
    expect(realtimeQueryMarkers({ type: "changed", entityType: "AircraftComponent" })).not.toContain("qms");
  });
});
