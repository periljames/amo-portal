import React, { useEffect, useMemo, useRef, useState } from "react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import {
  AlertTriangle,
  CalendarClock,
  CalendarDays,
  Download,
  Info,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { Link } from "react-router-dom";

import Drawer from "../../components/shared/Drawer";
import type {
  AuditProgramme,
  AuditProgrammeItem,
  AuditProgrammeScheduleLink,
  AuditUniverseItem,
} from "../../services/qmsAuditProgramme";
import {
  findAuditorScheduleCollisions,
  programmeMatrixSlotLabel,
  resolveAircraftRegistration,
  uniqueAuditorInitials,
  type AuditorScheduleAllocation,
  type AuditorScheduleCollision,
} from "./qmsAuditProgrammePlanning";
import {
  buildProgrammeMatrixRows,
  primaryProgrammeItem,
  rowHasProgrammeItems,
  type ProgrammeMatrixRow,
} from "./qmsAuditProgrammeMatrixModel";

const MONTHS = Array.from({ length: 12 }, (_, month) => ({
  month: month + 1,
  short: new Date(2000, month, 1).toLocaleString(undefined, { month: "short" }),
  long: new Date(2000, month, 1).toLocaleString(undefined, { month: "long" }),
}));

type MatrixRow = ProgrammeMatrixRow;

type MatrixView = "all" | "programme";
export type AuditKindView = "INTERNAL" | "EXTERNAL" | "BOTH";

type MonthEntry = {
  key: string;
  label: string;
  startDate: string;
  endDate: string;
  adjusted?: boolean;
  scheduled?: boolean;
};

type CollisionFocus = {
  item: AuditProgrammeItem;
  month: number;
  collisions: AuditorScheduleCollision[];
};

type Props = {
  programme: AuditProgramme;
  programmes: AuditProgramme[];
  year: number;
  items: AuditProgrammeItem[];
  coverageAreas: AuditUniverseItem[];
  scheduleLinks: AuditProgrammeScheduleLink[];
  auditorNames: ReadonlyMap<string, string>;
  programmeKindsById: ReadonlyMap<string, string>;
  editableProgrammeIds: ReadonlySet<string>;
  auditKindView: AuditKindView;
  editable: boolean;
  canSchedule: boolean;
  loading?: boolean;
  refreshing?: boolean;
  onProgrammeChange: (programmeId: string) => void;
  onAuditKindViewChange: (view: AuditKindView) => void;
  onYearChange: (year: number) => void;
  onRefresh: () => void;
  onHowItWorks: () => void;
  calendarHref: string;
  onEditProgramme?: () => void;
  onNewProgramme?: () => void;
  onDiscardProgramme?: () => void;
  onDownloadPdf?: () => void;
  downloadBusy?: boolean;
  onAddAudit: () => void;
  onAddCoverageArea: () => void;
  onAddAreaMonth: (area: AuditUniverseItem, month: number) => void;
  onEditMonth: (item: AuditProgrammeItem, month: number) => void;
  onViewItem: (item: AuditProgrammeItem) => void;
  onViewArea: (items: AuditProgrammeItem[], areaLabel: string) => void;
  onEditItem: (item: AuditProgrammeItem) => void;
  onScheduleItem: (item: AuditProgrammeItem) => void;
};

type MatrixActions = Pick<
  Props,
  | "editable"
  | "editableProgrammeIds"
  | "canSchedule"
  | "onAddAreaMonth"
  | "onEditMonth"
  | "onViewItem"
  | "onViewArea"
  | "onEditItem"
  | "onScheduleItem"
>;

type AuditorAssignment = {
  id: string;
  role: "lead" | "supporting" | "observer";
};

function auditorAssignments(
  item: AuditProgrammeItem | undefined,
): AuditorAssignment[] {
  if (!item) return [];
  return [
    item.lead_auditor_user_id
      ? { id: item.lead_auditor_user_id, role: "lead" as const }
      : null,
    ...(item.supporting_auditor_user_ids || []).map((id) => ({
      id,
      role: "supporting" as const,
    })),
    item.observer_auditor_user_id
      ? { id: item.observer_auditor_user_id, role: "observer" as const }
      : null,
  ].filter(
    (assignment): assignment is AuditorAssignment => assignment !== null,
  );
}

function AuditLeadInitials({
  item,
  auditorNames,
  auditorInitials,
}: {
  item: AuditProgrammeItem;
  auditorNames: ReadonlyMap<string, string>;
  auditorInitials: ReadonlyMap<string, string>;
}) {
  const leadId = item.lead_auditor_user_id;
  if (!leadId) return null;
  const fullName = auditorNames.get(leadId) || "Lead auditor";
  const initials = auditorInitials.get(leadId) || "??";
  return (
    <span
      className="qms-programme-matrix__assignees"
      aria-label={`Lead auditor ${fullName}`}
    >
      <b title={`${fullName} · Lead auditor`}>({initials})</b>
    </span>
  );
}

/** Observer + supporting only — lead is shown per slot chip. */
function AuditTeamRestInitials({
  item,
  auditorNames,
  auditorInitials,
}: {
  item: AuditProgrammeItem;
  auditorNames: ReadonlyMap<string, string>;
  auditorInitials: ReadonlyMap<string, string>;
}) {
  const assignments = auditorAssignments(item).filter(
    (assignment) => assignment.role !== "lead",
  );
  if (!assignments.length) return null;
  return (
    <span
      className="qms-programme-matrix__assignees"
      aria-label="Assigned audit team"
    >
      {assignments.map((assignment) => {
        const fullName = auditorNames.get(assignment.id) || "Assigned user";
        const initials = auditorInitials.get(assignment.id) || "??";
        const label = `(${initials})`;
        const title = `${fullName} · ${assignment.role === "observer" ? "Observer" : "Auditor"}`;
        if (assignment.role === "observer")
          return (
            <em key={`${assignment.role}:${assignment.id}`} title={title}>
              {label}
            </em>
          );
        return (
          <span key={`${assignment.role}:${assignment.id}`} title={title}>
            {label}
          </span>
        );
      })}
    </span>
  );
}

const MATRIX_DEFAULT_COL_DEF: ColDef<MatrixRow> = {
  suppressMovable: true,
  suppressHeaderMenuButton: true,
};

const getMatrixRowId = ({ data }: { data: MatrixRow }): string => data.id;

function human(value: string): string {
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dayOf(date: string | null | undefined): string {
  const day = Number(String(date || "").slice(8, 10));
  return Number.isFinite(day) && day > 0 ? String(day) : "—";
}

function monthOf(date: string | null | undefined): number | null {
  const month = Number(String(date || "").slice(5, 7));
  return month >= 1 && month <= 12 ? month : null;
}

function workingDayFor(year: number, monthDay: string): string {
  const requested = new Date(`${year}-${monthDay}T12:00:00`);
  if (Number.isNaN(requested.getTime())) return `${year}-${monthDay}`;
  const day = requested.getDay();
  if (day === 6) requested.setDate(requested.getDate() + 2);
  if (day === 0) requested.setDate(requested.getDate() + 1);
  return `${requested.getFullYear()}-${String(requested.getMonth() + 1).padStart(2, "0")}-${String(requested.getDate()).padStart(2, "0")}`;
}

function workingEndFor(startDate: string, durationDays = 1): string {
  const cursor = new Date(`${startDate}T12:00:00`);
  if (Number.isNaN(cursor.getTime())) return startDate;
  let elapsed = 1;
  while (elapsed < Math.max(1, durationDays)) {
    cursor.setDate(cursor.getDate() + 1);
    if (cursor.getDay() !== 0 && cursor.getDay() !== 6) elapsed += 1;
  }
  return `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}-${String(cursor.getDate()).padStart(2, "0")}`;
}

function entriesForMonth(
  item: AuditProgrammeItem,
  month: number,
  year: number,
  link?: AuditProgrammeScheduleLink,
): MonthEntry[] {
  if (item.recurrence === "FIXED_DATES") {
    return (item.fixed_dates || [])
      .filter((monthDay) => Number(monthDay.slice(0, 2)) === month)
      .map((monthDay) => {
        const requestedDate = `${year}-${monthDay}`;
        const occurrence = (link?.occurrences || []).find(
          (candidate) => candidate.requested_date === requestedDate,
        );
        const scheduledDate =
          occurrence?.scheduled_date || workingDayFor(year, monthDay);
        const adjusted = scheduledDate !== requestedDate;
        return {
          key: occurrence?.occurrence_key || requestedDate,
          label: adjusted
            ? `${dayOf(requestedDate)}→${dayOf(scheduledDate)}`
            : dayOf(requestedDate),
          startDate: scheduledDate,
          endDate: workingEndFor(
            scheduledDate,
            item.default_duration_days || 1,
          ),
          adjusted,
          scheduled: Boolean(occurrence),
        };
      });
  }

  if (link?.next_due_date && monthOf(link.next_due_date) === month) {
    return [
      {
        key: link.schedule_id || `${item.id}-${link.next_due_date}`,
        label: dayOf(link.next_due_date),
        startDate: link.next_due_date,
        endDate: workingEndFor(
          link.next_due_date,
          item.default_duration_days || 1,
        ),
        scheduled: true,
      },
    ];
  }

  if (item.target_start && monthOf(item.target_start) === month) {
    const range =
      item.target_end && item.target_end !== item.target_start
        ? `${dayOf(item.target_start)}–${dayOf(item.target_end)}`
        : dayOf(item.target_start);
    return [
      {
        key: `${item.id}-window`,
        label: range,
        startDate: item.target_start,
        endDate: item.target_end || item.target_start,
      },
    ];
  }
  return [];
}

function slotsForMonth(
  row: MatrixRow,
  month: number,
  year: number,
  linksByItem: ReadonlyMap<string, AuditProgrammeScheduleLink>,
): Array<{ item: AuditProgrammeItem; entry: MonthEntry }> {
  return row.items.flatMap((item) =>
    entriesForMonth(item, month, year, linksByItem.get(item.id)).map(
      (entry) => ({ item, entry }),
    ),
  );
}

function kindMatches(view: AuditKindView, kind?: string | null): boolean {
  if (view === "BOTH") return true;
  if (view === "INTERNAL") return kind === "INTERNAL";
  return kind === "EXTERNAL" || kind === "THIRD_PARTY";
}

function itemAllocations(
  items: readonly AuditProgrammeItem[],
  linksByItem: ReadonlyMap<string, AuditProgrammeScheduleLink>,
  year: number,
): AuditorScheduleAllocation[] {
  return items.flatMap((item) =>
    MONTHS.flatMap(({ month }) =>
      entriesForMonth(item, month, year, linksByItem.get(item.id)).map(
        (entry) => ({
          key: `${item.id}:${entry.key}`,
          itemId: item.id,
          programmeId: item.programme_id,
          title: item.title,
          startDate: entry.startDate,
          endDate: entry.endDate,
          auditorUserIds: auditorAssignments(item).map(
            (assignment) => assignment.id,
          ),
        }),
      ),
    ),
  );
}

function slotLabel(item: AuditProgrammeItem, label: string): string {
  return programmeMatrixSlotLabel(item, label);
}

function slotTitle(item: AuditProgrammeItem, entry: MonthEntry): string {
  const identity =
    resolveAircraftRegistration(item) || item.title || "Planned audit";
  const when = dateRangeLabel(entry.startDate, entry.endDate);
  const weekendNote = entry.adjusted
    ? " · Weekend moved to next working day"
    : "";
  return `${identity} · ${when}${weekendNote}`;
}

function dateRangeLabel(startDate: string, endDate: string): string {
  const format = (value: string) =>
    new Date(`${value}T12:00:00`).toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  return startDate === endDate
    ? format(startDate)
    : `${format(startDate)} – ${format(endDate)}`;
}

const QmsAuditProgrammeMatrix: React.FC<Props> = ({
  programme,
  programmes,
  year,
  items,
  coverageAreas,
  scheduleLinks,
  auditorNames,
  programmeKindsById,
  editableProgrammeIds,
  auditKindView,
  editable,
  canSchedule,
  loading = false,
  refreshing = false,
  onProgrammeChange,
  onAuditKindViewChange,
  onYearChange,
  onRefresh,
  onHowItWorks,
  calendarHref,
  onEditProgramme,
  onNewProgramme,
  onDiscardProgramme,
  onDownloadPdf,
  downloadBusy = false,
  onAddAudit,
  onAddCoverageArea,
  onAddAreaMonth,
  onEditMonth,
  onViewItem,
  onViewArea,
  onEditItem,
  onScheduleItem,
}) => {
  const [search, setSearch] = useState("");
  const [view, setView] = useState<MatrixView>("all");
  const [collisionFocus, setCollisionFocus] = useState<CollisionFocus | null>(
    null,
  );
  const linksByItem = useMemo(
    () => new Map(scheduleLinks.map((link) => [link.programme_item_id, link])),
    [scheduleLinks],
  );
  const visibleItems = useMemo(
    () =>
      items.filter((item) =>
        kindMatches(auditKindView, programmeKindsById.get(item.programme_id)),
      ),
    [auditKindView, items, programmeKindsById],
  );
  const visibleCoverageAreas = useMemo(
    () =>
      coverageAreas.filter((area) => {
        const kind = area.programme_kind || "BOTH";
        return kind === "BOTH" || kindMatches(auditKindView, kind);
      }),
    [auditKindView, coverageAreas],
  );
  const allRows = useMemo(
    () => buildProgrammeMatrixRows(visibleItems, visibleCoverageAreas),
    [visibleCoverageAreas, visibleItems],
  );
  const programmeRows = useMemo(
    () => allRows.filter((row) => rowHasProgrammeItems(row)),
    [allRows],
  );
  const plannedAuditCount = visibleItems.length;
  const publishedDates = useMemo(
    () =>
      scheduleLinks.reduce(
        (total, link) =>
          visibleItems.some((item) => item.id === link.programme_item_id)
            ? total +
              Math.max(link.occurrences?.length || 0, link.schedule_id ? 1 : 0)
            : total,
        0,
      ),
    [scheduleLinks, visibleItems],
  );
  const rows = useMemo(() => {
    const query = search.trim().toLowerCase();
    const visibleRows = view === "programme" ? programmeRows : allRows;
    if (!query) return visibleRows;
    return visibleRows.filter((row) =>
      [
        row.area.display_label,
        row.area.entity_type,
        row.area.risk_classification,
        ...row.items.map((item) => item.title),
        ...row.items.map((item) => item.audit_type),
      ].some((value) =>
        String(value || "")
          .toLowerCase()
          .includes(query),
      ),
    );
  }, [allRows, programmeRows, search, view]);
  const auditorInitials = useMemo(
    () =>
      uniqueAuditorInitials(
        [...auditorNames].map(([id, fullName]) => ({ id, fullName })),
      ),
    [auditorNames],
  );
  const collisionsByAllocation = useMemo(
    () =>
      findAuditorScheduleCollisions(
        itemAllocations(items, linksByItem, programme.programme_year),
      ),
    [items, linksByItem, programme.programme_year],
  );

  // AG Grid reconciles columns by object identity. React Query can trigger several
  // renders while requests recover, so keep handlers in a ref and rebuild the
  // column graph only when the programme year changes.
  const actionsRef = useRef<MatrixActions>({
    editable,
    editableProgrammeIds,
    canSchedule,
    onAddAreaMonth,
    onEditMonth,
    onViewItem,
    onViewArea,
    onEditItem,
    onScheduleItem,
  });
  useEffect(() => {
    actionsRef.current = {
      editable,
      editableProgrammeIds,
      canSchedule,
      onAddAreaMonth,
      onEditMonth,
      onViewItem,
      onViewArea,
      onEditItem,
      onScheduleItem,
    };
  }, [
    canSchedule,
    editable,
    editableProgrammeIds,
    onAddAreaMonth,
    onEditItem,
    onEditMonth,
    onScheduleItem,
    onViewArea,
    onViewItem,
  ]);

  const columns = useMemo<ColDef<MatrixRow>[]>(() => {
    const areaColumn: ColDef<MatrixRow> = {
      headerName: "Audit area",
      colId: "audit-area",
      pinned: "left",
      lockPinned: true,
      width: 250,
      minWidth: 220,
      maxWidth: 300,
      sortable: true,
      wrapText: true,
      autoHeight: true,
      cellClass: "qms-programme-matrix__area-cell",
      valueGetter: ({ data }) => data?.area.display_label || "",
      cellRenderer: ({ data }: ICellRendererParams<MatrixRow>) => {
        if (!data) return null;
        const actions = actionsRef.current;
        const primary = primaryProgrammeItem(data);
        const areaItems = data.items;
        const rowEditable = areaItems.some((item) =>
          actions.editableProgrammeIds.has(item.programme_id),
        );
        const openArea = () =>
          actions.onViewArea(areaItems, data.area.display_label);
        const openPrimaryEdit = () => {
          if (!primary) return;
          if (areaItems.length > 1) openArea();
          else actions.onEditItem(primary);
        };
        const areaLabel = (
          <strong>{data.area.display_label}</strong>
        );
        return (
          <div className="qms-programme-matrix__area">
            {areaItems.length ? (
              <button
                type="button"
                className="qms-programme-matrix__area-name"
                onClick={openArea}
                title={
                  areaItems.length > 1
                    ? `View ${areaItems.length} audits in ${data.area.display_label}`
                    : `Open ${primary?.title || data.area.display_label}`
                }
              >
                {areaLabel}
              </button>
            ) : (
              <span
                className="qms-programme-matrix__area-name"
                title={data.area.display_label}
              >
                {areaLabel}
              </span>
            )}
            <span className="qms-programme-matrix__row-actions">
              {areaItems.length ? (
                <button
                  type="button"
                  title={
                    areaItems.length > 1
                      ? `View ${areaItems.length} audits`
                      : "View audit"
                  }
                  aria-label={
                    areaItems.length > 1
                      ? `View ${areaItems.length} audits in ${data.area.display_label}`
                      : `View ${primary?.title || data.area.display_label}`
                  }
                  onClick={openArea}
                >
                  <Info size={14} />
                </button>
              ) : null}
              {primary && rowEditable ? (
                <button
                  type="button"
                  title={
                    areaItems.length > 1 ? "Choose audit to edit" : "Edit audit"
                  }
                  aria-label={
                    areaItems.length > 1
                      ? `Choose an audit to edit in ${data.area.display_label}`
                      : `Edit ${primary.title}`
                  }
                  onClick={openPrimaryEdit}
                >
                  <Pencil size={14} />
                </button>
              ) : null}
              {primary &&
              areaItems.length === 1 &&
              actions.canSchedule &&
              primary.state === "PLANNED" &&
              primary.recurrence !== "FIXED_DATES" ? (
                <button
                  type="button"
                  title="Schedule audit"
                  aria-label={`Schedule ${primary.title}`}
                  onClick={() => actions.onScheduleItem(primary)}
                >
                  <CalendarClock size={14} />
                </button>
              ) : null}
            </span>
          </div>
        );
      },
    };

    const monthColumns = MONTHS.map<ColDef<MatrixRow>>(
      ({ month, short, long }) => ({
        headerName: short,
        headerTooltip: `${long} ${programme.programme_year}`,
        colId: `month-${month}`,
        minWidth: 68,
        flex: 1,
        sortable: false,
        resizable: true,
        cellClass: "qms-programme-matrix__cell",
        cellRenderer: ({ data }: ICellRendererParams<MatrixRow>) => {
          if (!data) return null;
          const actions = actionsRef.current;
          const slots = slotsForMonth(
            data,
            month,
            programme.programme_year,
            linksByItem,
          );
          const focusItem = slots[0]?.item;
          const canPlanEmpty =
            actions.editable &&
            (data.items.length === 0 ||
              data.items.some((item) =>
                actions.editableProgrammeIds.has(item.programme_id),
              ) ||
              actions.editable);
          const slotCollisions = slots.flatMap(
            (slot) =>
              collisionsByAllocation.get(`${slot.item.id}:${slot.entry.key}`) ||
              [],
          );
          const openSlot = (item: AuditProgrammeItem) => {
            const slotEditable = actions.editableProgrammeIds.has(
              item.programme_id,
            );
            if (slotEditable) actions.onEditMonth(item, month);
            else actions.onViewItem(item);
          };
          const emptyLabel = `Add ${data.area.display_label} audit in ${long} ${programme.programme_year}`;
          return (
            <div className="qms-programme-matrix__slot">
              {slots.length ? (
                <div
                  className={`qms-programme-matrix__month has-plan${slots.some((slot) => slot.entry.scheduled) ? " is-scheduled" : ""}${slotCollisions.length ? " has-collision" : ""}`}
                >
                  {slots.slice(0, 2).map((slot) => {
                    const slotEditable = actions.editableProgrammeIds.has(
                      slot.item.programme_id,
                    );
                    return (
                      <button
                        key={`${slot.item.id}:${slot.entry.key}`}
                        type="button"
                        className={`qms-programme-matrix__chip${slot.entry.adjusted ? " is-adjusted" : ""}`}
                        title={slotTitle(slot.item, slot.entry)}
                        aria-label={`${slotTitle(slot.item, slot.entry)}. ${slotEditable ? "Click to edit dates." : "Click to view."}`}
                        onClick={() => openSlot(slot.item)}
                      >
                        <strong>
                          {slotLabel(slot.item, slot.entry.label)}
                        </strong>
                        <AuditLeadInitials
                          item={slot.item}
                          auditorNames={auditorNames}
                          auditorInitials={auditorInitials}
                        />
                      </button>
                    );
                  })}
                  {slots.length === 1 && focusItem ? (
                    <AuditTeamRestInitials
                      item={focusItem}
                      auditorNames={auditorNames}
                      auditorInitials={auditorInitials}
                    />
                  ) : null}
                  {slots.length > 2 ? (
                    <button
                      type="button"
                      className="qms-programme-matrix__more"
                      title={`View all ${slots.length} audits in ${long}`}
                      aria-label={`View all ${slots.length} audits for ${data.area.display_label} in ${long}`}
                      onClick={() =>
                        actions.onViewArea(
                          slots.map((slot) => slot.item),
                          `${data.area.display_label} · ${long}`,
                        )
                      }
                    >
                      +{slots.length - 2}
                    </button>
                  ) : null}
                </div>
              ) : canPlanEmpty ? (
                <button
                  type="button"
                  className="qms-programme-matrix__month"
                  aria-label={emptyLabel}
                  onClick={() => actions.onAddAreaMonth(data.area, month)}
                  title={`${emptyLabel}. Click to add.`}
                >
                  <span className="qms-programme-matrix__add">
                    <Plus size={14} aria-hidden />
                  </span>
                </button>
              ) : (
                <div className="qms-programme-matrix__month">
                  <span className="qms-programme-matrix__empty">—</span>
                </div>
              )}
              {focusItem && slotCollisions.length ? (
                <button
                  type="button"
                  className="qms-programme-matrix__collision"
                  aria-label={`Resolve ${slotCollisions.length} scheduling conflict${slotCollisions.length === 1 ? "" : "s"} for ${focusItem.title}`}
                  title="Auditor scheduling conflict"
                  onClick={() =>
                    setCollisionFocus({
                      item: focusItem,
                      month,
                      collisions: slotCollisions,
                    })
                  }
                >
                  <AlertTriangle size={13} aria-hidden />
                </button>
              ) : null}
            </div>
          );
        },
      }),
    );
    return [areaColumn, ...monthColumns];
  }, [
    auditorInitials,
    auditorNames,
    collisionsByAllocation,
    linksByItem,
    programme.programme_year,
  ]);

  return (
    <section
      className="qms-programme-matrix"
      aria-label={`${programme.programme_year} audit programme calendar`}
    >
      <header className="qms-programme-matrix__toolbar">
        <div className="qms-programme-matrix__selectors">
          <label className="qms-programme-matrix__programme-select">
            <span>Programme</span>
            <select
              value={programme.id}
              onChange={(event) => onProgrammeChange(event.target.value)}
            >
              {programmes.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.title} · {human(candidate.status)}
                </option>
              ))}
            </select>
          </label>
          <label className="qms-programme-matrix__year-select">
            <span>Year</span>
            <input
              type="number"
              min={2000}
              max={2200}
              value={year}
              onChange={(event) =>
                onYearChange(
                  Number(event.target.value) || new Date().getFullYear(),
                )
              }
            />
          </label>
        </div>
        <div className="qms-programme-matrix__actions">
          <label className="qms-programme-matrix__search">
            <Search size={15} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search audit area"
              aria-label="Search audit programme"
            />
          </label>
          <button
            type="button"
            className="is-icon"
            title="How this programme works"
            aria-label="How this programme works"
            onClick={onHowItWorks}
          >
            <Info size={15} />
          </button>
          <Link
            className="is-icon"
            title="Open Calendar"
            aria-label="Open Calendar"
            to={calendarHref}
          >
            <CalendarDays size={15} />
          </Link>
          {onEditProgramme ? (
            <button
              type="button"
              className="is-icon"
              title="Edit programme"
              aria-label="Edit programme"
              onClick={onEditProgramme}
            >
              <Pencil size={15} />
            </button>
          ) : null}
          {onDownloadPdf ? (
            <button
              type="button"
              className="is-icon"
              title="Download programme PDF"
              aria-label="Download programme PDF"
              onClick={onDownloadPdf}
              disabled={downloadBusy}
            >
              <Download size={15} />
            </button>
          ) : null}
          {onDiscardProgramme ? (
            <button
              type="button"
              className="is-icon is-danger"
              title="Discard draft programme"
              aria-label="Discard draft programme"
              onClick={onDiscardProgramme}
            >
              <Trash2 size={15} />
            </button>
          ) : null}
          <button
            type="button"
            className="is-icon"
            title="Refresh programme"
            aria-label="Refresh programme"
            onClick={onRefresh}
            disabled={refreshing}
          >
            <RefreshCw size={15} />
          </button>
          {onNewProgramme ? (
            <button
              type="button"
              className="is-icon"
              title="New programme"
              aria-label="New programme"
              onClick={onNewProgramme}
            >
              <Plus size={15} />
            </button>
          ) : null}
          {editable ? (
            allRows.length ? (
              <button type="button" className="is-primary" onClick={onAddAudit}>
                <Plus size={15} /> Add audit
              </button>
            ) : (
              <button
                type="button"
                className="is-primary"
                onClick={onAddCoverageArea}
              >
                <Plus size={15} /> Add audit area
              </button>
            )
          ) : null}
        </div>
      </header>

      <div className="qms-programme-matrix__viewbar">
        <div
          className="qms-programme-matrix__kind-switch"
          aria-label="Audit type view"
        >
          {(["INTERNAL", "EXTERNAL", "BOTH"] as const).map((kind) => (
            <button
              key={kind}
              type="button"
              className={auditKindView === kind ? "is-active" : ""}
              aria-pressed={auditKindView === kind}
              onClick={() => onAuditKindViewChange(kind)}
            >
              {kind === "BOTH"
                ? "Both"
                : kind === "INTERNAL"
                  ? "Internal"
                  : "External"}
            </button>
          ))}
        </div>
        <div
          className="qms-programme-matrix__views"
          aria-label="Audit area view"
        >
          <button
            type="button"
            className={view === "all" ? "is-active" : ""}
            aria-pressed={view === "all"}
            onClick={() => setView("all")}
          >
            All areas <span>{allRows.length}</span>
          </button>
          <button
            type="button"
            className={view === "programme" ? "is-active" : ""}
            aria-pressed={view === "programme"}
            onClick={() => setView("programme")}
          >
            In programme <span>{programmeRows.length}</span>
          </button>
        </div>
        <p aria-live="polite">
          <strong>{plannedAuditCount}</strong> planned audits{" "}
          <span aria-hidden>·</span> <strong>{programmeRows.length}</strong>{" "}
          audit areas <span aria-hidden>·</span>{" "}
          <strong>{publishedDates}</strong> calendar dates
        </p>
      </div>

      <div className="qms-programme-grid qms-programme-matrix__grid ag-theme-alpine">
        <AgGridReact<MatrixRow>
          key={`${programme.id}:${programme.programme_year}`}
          rowData={rows}
          columnDefs={columns}
          defaultColDef={MATRIX_DEFAULT_COL_DEF}
          getRowId={getMatrixRowId}
          rowHeight={64}
          headerHeight={40}
          animateRows={false}
          loading={loading}
          overlayNoRowsTemplate={
            view === "programme"
              ? '<span class="qms-programme-matrix__overlay">No audits are in this programme yet. Switch to All areas and choose a month to plan one.</span>'
              : '<span class="qms-programme-matrix__overlay">No audit areas yet. Add an audit area to begin planning.</span>'
          }
        />
      </div>
      {!loading && allRows.length > 0 && !rows.length ? (
        <p className="qms-programme-matrix__no-results">
          No audit areas match “{search}”.
        </p>
      ) : null}
      <footer className="qms-programme-matrix__legend">
        <span>
          <i className="is-planned" /> Planned
        </span>
        <span>
          <i className="is-scheduled" /> Published to Calendar
        </span>
        <span>
          <i className="is-adjusted" /> Weekend moved to next working day
        </span>
        <span>
          <i className="is-collision" /> Auditor conflict
        </span>
      </footer>
      <Drawer
        title="Auditor scheduling conflict"
        isOpen={Boolean(collisionFocus)}
        onClose={() => setCollisionFocus(null)}
        side="right"
        panelClassName="qms-programme-collision-drawer"
      >
        {collisionFocus ? (
          <>
            <div className="qms-programme-collision-drawer__body">
              <p>
                <strong>{collisionFocus.item.title}</strong> overlaps another
                commitment assigned to the same audit team member.
              </p>
              <div className="qms-programme-collision-list">
                {collisionFocus.collisions.map((collision, index) => (
                  <article
                    key={`${collision.otherItemId}:${collision.startDate}:${index}`}
                  >
                    <AlertTriangle size={16} aria-hidden />
                    <div>
                      <strong>{collision.otherTitle}</strong>
                      <span>
                        {dateRangeLabel(collision.startDate, collision.endDate)}
                      </span>
                      <small>
                        Shared:{" "}
                        {collision.conflictingUserIds
                          .map(
                            (userId) =>
                              auditorNames.get(userId) || "Assigned auditor",
                          )
                          .join(", ")}
                      </small>
                    </div>
                  </article>
                ))}
              </div>
            </div>
            <div className="qms-programme-collision-drawer__footer">
              <button
                type="button"
                className="is-secondary"
                onClick={() => setCollisionFocus(null)}
              >
                Close
              </button>
              {editableProgrammeIds.has(collisionFocus.item.programme_id) ? (
                <>
                  <button
                    type="button"
                    className="is-secondary"
                    onClick={() => {
                      const target = collisionFocus;
                      setCollisionFocus(null);
                      onEditItem(target.item);
                    }}
                  >
                    Assign another lead
                  </button>
                  <button
                    type="button"
                    className="is-primary"
                    onClick={() => {
                      const target = collisionFocus;
                      setCollisionFocus(null);
                      onEditMonth(target.item, target.month);
                    }}
                  >
                    Reschedule audit
                  </button>
                </>
              ) : (
                <Link className="is-primary" to={calendarHref}>
                  Open Calendar
                </Link>
              )}
            </div>
          </>
        ) : null}
      </Drawer>
    </section>
  );
};

export default QmsAuditProgrammeMatrix;
