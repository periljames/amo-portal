import type {
  AuditProgrammeItem,
  AuditProgrammeScheduleLink,
  AuditUniverseItem,
} from "../../services/qmsAuditProgramme";

export type ProgrammeMatrixRow = {
  id: string;
  area: AuditUniverseItem;
  /** All programme items for this audit area — months share one row. */
  items: AuditProgrammeItem[];
};

/**
 * One matrix row per audit area. Additional planned months must never create
 * duplicate area rows; they land in the matching month column on this row.
 */
export function buildProgrammeMatrixRows(
  items: AuditProgrammeItem[],
  coverageAreas: AuditUniverseItem[],
): ProgrammeMatrixRow[] {
  const linked = new Map<string, AuditProgrammeItem[]>();
  items.forEach((item) => {
    const entries = linked.get(item.universe_item_id) || [];
    entries.push(item);
    linked.set(item.universe_item_id, entries);
  });

  const rows: ProgrammeMatrixRow[] = [];
  coverageAreas
    .filter((area) => area.active)
    .sort((left, right) =>
      left.display_label.localeCompare(right.display_label),
    )
    .forEach((area) => {
      const areaItems = [...(linked.get(area.id) || [])].sort(
        (left, right) =>
          String(left.target_start || "").localeCompare(
            String(right.target_start || ""),
          ) || left.title.localeCompare(right.title),
      );
      rows.push({
        id: `area-${area.id}`,
        area,
        items: areaItems,
      });
      linked.delete(area.id);
    });

  linked.forEach((areaItems, universeItemId) => {
    const sorted = [...areaItems].sort(
      (left, right) =>
        String(left.target_start || "").localeCompare(
          String(right.target_start || ""),
        ) || left.title.localeCompare(right.title),
    );
    const sample = sorted[0];
    const area = sample?.auditable_entity || {
      id: universeItemId,
      entity_type: "OTHER" as const,
      display_label: "Unlinked audit area",
      source_owner_module: "AUDIT_PROGRAMME",
      source_type: "OTHER",
      source_id: universeItemId,
      risk_classification: "MEDIUM" as const,
      regulatory_criticality: "MEDIUM" as const,
      mandatory_surveillance: false,
      active: true,
    };
    rows.push({
      id: `area-${area.id}`,
      area,
      items: sorted,
    });
  });

  return rows;
}

export function primaryProgrammeItem(
  row: Pick<ProgrammeMatrixRow, "items">,
): AuditProgrammeItem | undefined {
  return row.items[0];
}

export function rowHasProgrammeItems(
  row: Pick<ProgrammeMatrixRow, "items">,
): boolean {
  return row.items.length > 0;
}

export type ProgrammeMonthSlot = {
  item: AuditProgrammeItem;
  entryKey: string;
  label: string;
  startDate: string;
  endDate: string;
  adjusted?: boolean;
  scheduled?: boolean;
  scheduleLink?: AuditProgrammeScheduleLink;
};
