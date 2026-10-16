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
});
