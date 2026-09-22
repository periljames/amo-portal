import { describe, expect, it } from "vitest";

import {
  buildProgrammeMatrixRows,
  primaryProgrammeItem,
  rowHasProgrammeItems,
} from "./qmsAuditProgrammeMatrixModel";
import type {
  AuditProgrammeItem,
  AuditUniverseItem,
} from "../../services/qmsAuditProgramme";

function area(id: string, label: string): AuditUniverseItem {
  return {
    id,
    entity_type: "FACILITY",
    display_label: label,
    source_owner_module: "AUDIT_PROGRAMME",
    source_type: "FACILITY",
    source_id: id,
    risk_classification: "MEDIUM",
    regulatory_criticality: "MEDIUM",
    mandatory_surveillance: false,
    active: true,
  };
}

function item(
  id: string,
  universeItemId: string,
  title: string,
  targetStart: string,
): AuditProgrammeItem {
  return {
    id,
    programme_id: "prog-1",
    universe_item_id: universeItemId,
    title,
    audit_type: "FACILITY",
    scope: "Facility surveillance",
    criteria: [],
    mandatory_surveillance: false,
    prioritization_basis: [],
    recurrence: "ONE_TIME",
    fixed_dates: [],
    target_start: targetStart,
    target_end: targetStart,
    state: "PLANNED",
    supporting_auditor_user_ids: [],
    default_duration_days: 1,
  };
}

describe("buildProgrammeMatrixRows", () => {
  it("keeps one row per audit area when multiple months are planned", () => {
    const hangar = area("hangar", "Hangar");
    const shop = area("shop", "Workshop");
    const rows = buildProgrammeMatrixRows(
      [
        item("jan", "hangar", "Hangar Jan", "2026-01-12"),
        item("mar", "hangar", "Hangar Mar", "2026-03-08"),
        item("jun", "shop", "Workshop Jun", "2026-06-01"),
      ],
      [hangar, shop],
    );

    expect(rows).toHaveLength(2);
    expect(rows.map((row) => row.area.id)).toEqual(["hangar", "shop"]);
    expect(rows[0].items.map((entry) => entry.id)).toEqual(["jan", "mar"]);
    expect(rows[1].items.map((entry) => entry.id)).toEqual(["jun"]);
    expect(rowHasProgrammeItems(rows[0])).toBe(true);
    expect(primaryProgrammeItem(rows[0])?.id).toBe("jan");
  });

  it("still renders empty coverage areas so months can be planned", () => {
    const hangar = area("hangar", "Hangar");
    const rows = buildProgrammeMatrixRows([], [hangar]);
    expect(rows).toEqual([{ id: "area-hangar", area: hangar, items: [] }]);
  });
});
