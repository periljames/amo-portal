import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CalendarCheck2,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  Download,
  FileCheck2,
  Info,
  Library,
  LockKeyhole,
  Pencil,
  Plane,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  UserCheck,
} from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { hasQmsRolePermission } from "../../app/routeGuards";
import { useToast } from "../../components/feedback/ToastProvider";
import QmsCalendarSyncDialog from "../../components/QMS/QmsCalendarSyncDialog";
import Drawer from "../../components/shared/Drawer";
import { HistoryTextarea } from "../../components/shared/HistoryTextarea";
import {
  fieldHistoryAreaFromEntity,
  historyEntriesFromValue,
  useTextFieldHistory,
} from "../../hooks/useTextFieldHistory";
import { getCachedUser } from "../../services/auth";
import {
  addAuditProgrammeItem,
  createAuditProgramme,
  createAuditProgrammeAmendment,
  createAuditUniverseItem,
  downloadAuditProgrammeSchedule,
  ensureAuditUniverseDefaults,
  getAuditProgramme,
  getAuditProgrammeOptimizer,
  getPlannerScheduleOptions,
  listAuditProgrammeScheduleLinks,
  listAuditProgrammeSchedulingQueue,
  listAuditProgrammes,
  listAuditUniverse,
  readinessOf,
  rebuildAuditProgrammeOptimizer,
  reviewAuditProgramme,
  transitionAuditProgramme,
  updateAuditProgramme,
  updateAuditProgrammeItem,
  updateAuditUniverseItem,
  type AuditAssuranceModel,
  type AuditProgramme,
  type AuditProgrammeItem,
  type AuditProgrammeRecurrence,
  type AuditProgrammeList,
  type AuditProgrammeStatus,
  type AuditRiskLevel,
  type AuditUniverseEntityType,
  type AuditUniverseItem,
  type AuditUniverseProgrammeKind,
} from "../../services/qmsAuditProgramme";
import { listAircraft, type AircraftRead } from "../../services/fleet";
import {
  ProgrammeLocationSelect,
  ProgrammeObserverSelect,
  SupportingAuditorPicker,
} from "./QmsAuditPlanningFields";
import QmsAuditProgrammeSchedulePanel from "./QmsAuditProgrammeSchedulePanel";
import QmsAuditProgrammeMatrix, {
  type AuditKindView,
} from "./QmsAuditProgrammeMatrix";
import {
  programmeApprovalStage,
  programmeIsControlled,
} from "./qmsAuditProgrammeApproval";
import {
  auditMonthPlanningMode,
  auditTypeForEntity,
  auditTypeLabel,
  programmeLeadAuditorOptions,
  resolveAircraftRegistration,
  suggestedLocationCode,
  withoutLeadAuditor,
  workingDayCount,
} from "./qmsAuditProgrammePlanning";
import {
  PROGRAMME_KINDS,
  availableProgrammeKinds,
  canCreateAnotherProgramme,
  carryForwardResultToast,
  defaultCopyPreviousYear,
  defaultRotateAuditors,
  emptyYearCreateHint,
  emptyYearCreateLabel,
  headProgrammesForYear,
  priorYearCarryForwardAvailable,
  programmeDisplayLabel,
  programmeKindOf,
  programmeKindTitle,
  programmeStatusHint,
  type ProgrammeKind,
} from "./qmsAuditProgrammeDisplay";
import "../../styles/qms-audit-programme.css";
import "../../styles/qms-audit-programme-workflow.css";
import "../../styles/qms-audit-programme-polish.css";
import "../../styles/qms-assurance-cta-hierarchy.css";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";

const RECURRENCES: Array<{ value: AuditProgrammeRecurrence; label: string }> = [
  { value: "FIXED_DATES", label: "Specific dates each year" },
  { value: "ONE_TIME", label: "One time" },
  { value: "MONTHLY", label: "Monthly" },
  { value: "QUARTERLY", label: "Quarterly" },
  { value: "SEMI_ANNUAL", label: "Every six months" },
  { value: "ANNUAL", label: "Once a year" },
];
const UNIVERSE_TYPES: AuditUniverseEntityType[] = [
  "DEPARTMENT",
  "FACILITY",
  "STATION",
  "SUPPLIER",
  "CONTRACTOR",
  "PROCESS",
  "CAPABILITY",
  "APPROVAL_RATING",
  "AIRCRAFT",
  "AIRCRAFT_TYPE",
  "PERSONNEL_GROUP",
  "OTHER",
];
const RISKS: AuditRiskLevel[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const SCHEDULABLE_RECURRENCES = new Set([
  "ONE_TIME",
  "MONTHLY",
  "QUARTERLY",
  "SEMI_ANNUAL",
  "ANNUAL",
]);
const METHODOLOGY_PILLARS: Array<{
  id: AuditAssuranceModel;
  label: string;
  hint: string;
}> = [
  {
    id: "COMPLIANCE",
    label: "Compliance",
    hint: "Regulatory / contractual floor",
  },
  { id: "RISK", label: "Risk", hint: "Inherent & residual exposure" },
  { id: "PERFORMANCE", label: "Performance", hint: "Findings, trends, KPIs" },
  {
    id: "HYBRID",
    label: "Hybrid",
    hint: "Combines compliance, risk, and performance",
  },
];

const AUDIT_AREA_DEFAULT_COL_DEF: ColDef<AuditUniverseItem> = {
  sortable: true,
  resizable: true,
  suppressMovable: true,
};

const getAuditAreaRowId = ({ data }: { data: AuditUniverseItem }): string =>
  data.id;

type WorkspaceTab = "requirements" | "universe" | "readiness";

type CalendarMonthTarget = {
  item: AuditProgrammeItem;
  month: number;
  mode: "create" | "update";
};

function human(value: string): string {
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateLabel(value?: string | null): string {
  if (!value) return "Not set";
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      });
}

function programmeItemIdentity(item: AuditProgrammeItem): string {
  return resolveAircraftRegistration(item) || item.title || "Planned audit";
}

function programmeItemWindowLabel(
  item: AuditProgrammeItem,
  year: number,
): string {
  if (item.recurrence === "FIXED_DATES" && item.fixed_dates?.length) {
    return item.fixed_dates
      .map((value) => fixedDateLabel(value, year))
      .join(" · ");
  }
  if (item.target_start) {
    return item.target_end && item.target_end !== item.target_start
      ? `${dateLabel(item.target_start)} → ${dateLabel(item.target_end)}`
      : dateLabel(item.target_start);
  }
  return human(item.recurrence || "PLANNED");
}

function programmeItemPrimaryMonth(item: AuditProgrammeItem): number {
  if (item.fixed_dates?.length) {
    const month = Number(String(item.fixed_dates[0]).slice(0, 2));
    if (month >= 1 && month <= 12) return month;
  }
  if (item.target_start) {
    const month = Number(String(item.target_start).slice(5, 7));
    if (month >= 1 && month <= 12) return month;
  }
  return 0;
}

function groupAreaAuditsByMonth(
  items: readonly AuditProgrammeItem[],
): Array<{ month: number; label: string; items: AuditProgrammeItem[] }> {
  const buckets = new Map<number, AuditProgrammeItem[]>();
  for (const item of items) {
    const month = programmeItemPrimaryMonth(item);
    const bucket = buckets.get(month);
    if (bucket) bucket.push(item);
    else buckets.set(month, [item]);
  }
  return Array.from(buckets.entries())
    .sort(([left], [right]) => {
      if (left === 0) return 1;
      if (right === 0) return -1;
      return left - right;
    })
    .map(([month, monthItems]) => ({
      month,
      label:
        month >= 1 && month <= 12
          ? new Date(2000, month - 1, 1).toLocaleString(undefined, {
              month: "long",
            })
          : "Unscheduled",
      items: monthItems,
    }));
}

function normalizeAssuranceModel(value?: string | null): AuditAssuranceModel {
  const normalized = String(value || "HYBRID").toUpperCase();
  if (
    normalized === "COMPLIANCE" ||
    normalized === "PERFORMANCE" ||
    normalized === "RISK"
  )
    return normalized;
  return "HYBRID";
}

function methodologyLabel(model?: string | null): string {
  const normalized = normalizeAssuranceModel(model);
  if (normalized === "COMPLIANCE") return "Compliance-based";
  if (normalized === "RISK") return "Risk-based";
  if (normalized === "PERFORMANCE") return "Performance-based";
  return "Hybrid";
}

function statusTone(
  status: string,
): "good" | "warn" | "muted" | "neutral" | "danger" {
  const value = status.toUpperCase();
  if (["ACTIVE", "SCHEDULED", "COMPLETED", "APPROVED"].includes(value))
    return "good";
  if (["UNDER_REVIEW", "PLANNED", "FOLLOW_UP_REQUIRED"].includes(value))
    return "warn";
  if (["DEFERRED", "CANCELLED", "SUPERSEDED", "CLOSED"].includes(value))
    return "muted";
  if (["DRAFT"].includes(value)) return "neutral";
  return "neutral";
}

function linesOf(
  values?: Array<string | Record<string, unknown>> | null,
): string {
  return (values || [])
    .map((entry) => (typeof entry === "string" ? entry : JSON.stringify(entry)))
    .filter(Boolean)
    .join("\n");
}

function weekendAdjustment(value: string): string | null {
  if (!value) return null;
  const requested = new Date(`${value}T12:00:00`);
  const day = requested.getDay();
  if (day !== 0 && day !== 6) return null;
  const adjusted = new Date(requested);
  adjusted.setDate(requested.getDate() + (day === 6 ? 2 : 1));
  return `Weekend — schedules on ${adjusted.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}`;
}

function fixedDateLabel(monthDay: string, year: number): string {
  const value = new Date(`${year}-${monthDay}T12:00:00`);
  return Number.isNaN(value.getTime())
    ? monthDay
    : value.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function programmeDate(year: number, month: number, day = 15): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function programmeEditable(status?: AuditProgrammeStatus | null): boolean {
  return status === "DRAFT";
}

type AuditAreaGridContext = {
  canManage: boolean;
  selected: AuditProgramme | undefined;
  selectedProgrammeId: string | null;
  linkedRequirementCount: (universeItemId: string) => number;
  open: (item: AuditUniverseItem, edit: boolean) => void;
  remove: (item: AuditUniverseItem) => void;
  schedule: (item: AuditUniverseItem) => void;
};

function auditAreaGridContext(
  params: ICellRendererParams<AuditUniverseItem>,
): AuditAreaGridContext {
  return params.context as AuditAreaGridContext;
}

const AUDIT_AREA_COLUMNS: ColDef<AuditUniverseItem>[] = [
  {
    headerName: "Audit area",
    colId: "audit-area",
    field: "display_label",
    flex: 2,
    minWidth: 220,
    cellRenderer: ({ data }: ICellRendererParams<AuditUniverseItem>) =>
      data ? (
        <span className="qms-programme-grid__primary">
          <strong>{data.aircraft?.tail_number || data.display_label}</strong>
          <small>
            {data.aircraft
              ? `${data.aircraft.model || "Model not recorded"} · MSN ${data.aircraft.msn}`
              : `${human(data.entity_type)}${data.active ? "" : " · Removed"}`}
          </small>
        </span>
      ) : null,
  },
  {
    headerName: "Risk",
    colId: "risk",
    field: "risk_classification",
    flex: 0.8,
    minWidth: 105,
  },
  {
    headerName: "Source",
    colId: "source",
    field: "origin",
    flex: 1,
    minWidth: 125,
    valueGetter: ({ data }) =>
      data?.origin === "PLATFORM_STANDARD"
        ? "Portal standard"
        : data?.entity_type === "AIRCRAFT"
          ? "Fleet register"
          : "Tenant area",
  },
  {
    headerName: "In programme",
    colId: "programme-count",
    flex: 0.9,
    minWidth: 120,
    valueGetter: (params) => {
      const current = params.context as AuditAreaGridContext;
      return params.data && current.selectedProgrammeId
        ? current.linkedRequirementCount(params.data.id)
        : 0;
    },
    valueFormatter: ({ value }) =>
      Number(value)
        ? `${value} audit${Number(value) === 1 ? "" : "s"}`
        : "Not included",
  },
  {
    headerName: "Actions",
    colId: "actions",
    sortable: false,
    filter: false,
    width: 142,
    minWidth: 142,
    pinned: "right",
    cellRenderer: (params: ICellRendererParams<AuditUniverseItem>) => {
      const { data } = params;
      if (!data) return null;
      const current = auditAreaGridContext(params);
      const programme = current.selected;
      return (
        <span className="qms-programme-grid__actions">
          <button
            type="button"
            className="is-icon"
            title="View audit area"
            aria-label={`View ${data.display_label}`}
            onClick={() => current.open(data, false)}
          >
            <Info size={15} />
          </button>
          {current.canManage ? (
            <button
              type="button"
              className="is-icon"
              title="Edit audit area"
              aria-label={`Edit ${data.display_label}`}
              onClick={() => current.open(data, true)}
            >
              <Pencil size={15} />
            </button>
          ) : null}
          {current.canManage && data.active ? (
            <button
              type="button"
              className="is-icon is-danger"
              title="Remove from this tenant's catalogue"
              aria-label={`Remove ${data.display_label}`}
              onClick={() => current.remove(data)}
            >
              <Trash2 size={15} />
            </button>
          ) : null}
          {programme &&
          current.canManage &&
          programmeEditable(programme.status) &&
          data.active &&
          !current.linkedRequirementCount(data.id) ? (
            <button
              type="button"
              className="is-icon is-schedule"
              title={`Schedule in ${programmeDisplayLabel(programme)}`}
              aria-label={`Add ${data.display_label} to programme`}
              onClick={() => current.schedule(data)}
            >
              <Plus size={15} />
            </button>
          ) : null}
        </span>
      );
    },
  },
];

const QmsAuditProgrammePageV2: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const objectivesHistory = useTextFieldHistory(amoCode, "programme-objectives", {
    areaScope: "PROGRAMME",
  });
  const basisHistory = useTextFieldHistory(amoCode, "programme-regulatory-basis", {
    areaScope: "PROGRAMME",
  });
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [selectedId, setSelectedId] = useState<string | null>(() => searchParams.get("programme"));
  const [workspaceTab, setWorkspaceTab] =
    useState<WorkspaceTab>(() => searchParams.get("tab") === "approval" ? "readiness" : "requirements");
  const [auditKindView, setAuditKindView] = useState<AuditKindView>("INTERNAL");
  const [showCreate, setShowCreate] = useState(false);
  const [showProgrammeDetail, setShowProgrammeDetail] = useState(false);
  const [showMethodologyInfo, setShowMethodologyInfo] = useState(false);
  const [showProgrammeEdit, setShowProgrammeEdit] = useState(false);
  const [cancelItemReason, setCancelItemReason] = useState("");
  const [cancelItemTarget, setCancelItemTarget] =
    useState<AuditProgrammeItem | null>(null);
  const [showRequirement, setShowRequirement] = useState(false);
  const [requirementFocus, setRequirementFocus] =
    useState<AuditProgrammeItem | null>(null);
  const [requirementEditMode, setRequirementEditMode] = useState(false);
  const [areaAuditsFocus, setAreaAuditsFocus] = useState<{
    areaLabel: string;
    items: AuditProgrammeItem[];
  } | null>(null);
  const [showUniverseCreate, setShowUniverseCreate] = useState(false);
  const [universeFocus, setUniverseFocus] = useState<AuditUniverseItem | null>(
    null,
  );
  const [universeEditMode, setUniverseEditMode] = useState(false);
  const [removeUniverseTarget, setRemoveUniverseTarget] =
    useState<AuditUniverseItem | null>(null);
  const [areaKind, setAreaKind] =
    useState<Exclude<AuditUniverseProgrammeKind, "BOTH">>("INTERNAL");
  const [showInactiveAreas, setShowInactiveAreas] = useState(false);
  const [scheduleTarget, setScheduleTarget] = useState<{
    programmeId: string;
    itemId: string;
  } | null>(null);
  const [calendarMonthTarget, setCalendarMonthTarget] =
    useState<CalendarMonthTarget | null>(null);
  const [actionReason, setActionReason] = useState("");
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [discardReason, setDiscardReason] = useState("");
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);
  const [downloadBusy, setDownloadBusy] = useState<"pdf" | "ics" | null>(null);
  const [calendarSyncOpen, setCalendarSyncOpen] = useState(false);
  const [editReason, setEditReason] = useState("");
  const currentUser = getCachedUser();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const canQualityReview = hasQmsRolePermission("qms.audit.programme.quality_review");
  const canApprove = hasQmsRolePermission("qms.audit.programme.approve");
  const canExport = hasQmsRolePermission("qms.reports.export");
  const plannerHref = `/maintenance/${encodeURIComponent(amoCode)}/quality/calendar/week`;

  const programmesQuery = useQuery({
    queryKey: ["qms-audit-programmes", amoCode.trim().toLowerCase(), year],
    queryFn: ({ signal }) => listAuditProgrammes(amoCode, year, signal),
    staleTime: 5_000,
  });
  const priorYearQuery = useQuery({
    queryKey: ["qms-audit-programmes", amoCode.trim().toLowerCase(), year - 1],
    queryFn: ({ signal }) => listAuditProgrammes(amoCode, year - 1, signal),
    enabled: canManage,
    staleTime: 30_000,
  });
  const universeQuery = useQuery({
    queryKey: ["qms-audit-universe", amoCode.trim().toLowerCase()],
    queryFn: ({ signal }) => listAuditUniverse(amoCode, signal),
    staleTime: 10_000,
  });
  const standardAreasQuery = useQuery({
    queryKey: ["qms-audit-universe-standards", amoCode],
    queryFn: () => ensureAuditUniverseDefaults(amoCode),
    enabled: canManage && workspaceTab === "universe",
    staleTime: 60 * 60_000,
    retry: 1,
  });
  const peopleQuery = useQuery({
    queryKey: ["qms-planner-schedule-options", amoCode],
    queryFn: ({ signal }) => getPlannerScheduleOptions(amoCode, signal),
    enabled: canManage,
    staleTime: 30_000,
  });
  const queueQuery = useQuery({
    queryKey: ["qms-audit-programme-scheduling-queue", amoCode.trim().toLowerCase()],
    queryFn: ({ signal }) => listAuditProgrammeSchedulingQueue(amoCode, signal),
    enabled: canManage,
    staleTime: 5_000,
  });
  const programmes = useMemo(
    () => programmesQuery.data?.items || [],
    [programmesQuery.data?.items],
  );
  const priorYearProgrammes = useMemo(
    () => priorYearQuery.data?.items || [],
    [priorYearQuery.data?.items],
  );
  const priorYear = year - 1;
  const canCarryForwardDefaultKind = useMemo(() => {
    const kind = availableProgrammeKinds(programmes)[0] || "INTERNAL";
    return priorYearCarryForwardAvailable(priorYearProgrammes, kind);
  }, [priorYearProgrammes, programmes]);
  const visibleProgrammes = useMemo(
    () => headProgrammesForYear(programmes),
    [programmes],
  );
  useEffect(() => {
    if (!selectedId) return;
    if (visibleProgrammes.some((programme) => programme.id === selectedId)) return;
    setSelectedId(null);
    const next = new URLSearchParams(searchParams);
    if (next.has("programme")) {
      next.delete("programme");
      setSearchParams(next, { replace: true });
    }
  }, [selectedId, visibleProgrammes, searchParams, setSearchParams]);
  const matrixPortfolioQuery = useQuery({
    queryKey: [
      "qms-audit-programme-matrix-portfolio",
      amoCode,
      year,
      visibleProgrammes.map((programme) => programme.id).join(","),
    ],
    queryFn: async ({ signal }) =>
      Promise.all(
        visibleProgrammes.map(async (programme) => ({
          programme: await getAuditProgramme(amoCode, programme.id, signal),
          scheduleLinks: (
            await listAuditProgrammeScheduleLinks(amoCode, programme.id, signal)
          ).items,
        })),
      ),
    enabled: workspaceTab === "requirements" && visibleProgrammes.length > 0,
    staleTime: 3_000,
  });
  const creatableKinds = useMemo(
    () => availableProgrammeKinds(programmes),
    [programmes],
  );
  const allowCreateProgramme =
    canManage && canCreateAnotherProgramme(programmes);
  const selectedProgrammeId = selectedId || visibleProgrammes[0]?.id || null;
  const selectedProgrammeSummary = visibleProgrammes.find(
    (programme) => programme.id === selectedProgrammeId,
  );
  const detailQuery = useQuery({
    queryKey: ["qms-audit-programme", amoCode, selectedProgrammeId],
    queryFn: ({ signal }) =>
      getAuditProgramme(amoCode, selectedProgrammeId as string, signal),
    enabled: Boolean(selectedProgrammeId),
    staleTime: 3_000,
  });
  const optimizerQuery = useQuery({
    queryKey: ["qms-audit-programme-optimizer", amoCode, selectedProgrammeId],
    queryFn: ({ signal }) =>
      getAuditProgrammeOptimizer(
        amoCode,
        selectedProgrammeId as string,
        signal,
      ),
    enabled: Boolean(selectedProgrammeId),
    staleTime: 3_000,
  });
  const scheduleLinksQuery = useQuery({
    queryKey: [
      "qms-audit-programme-schedule-links",
      amoCode,
      selectedProgrammeId,
    ],
    queryFn: ({ signal }) =>
      listAuditProgrammeScheduleLinks(
        amoCode,
        selectedProgrammeId as string,
        signal,
      ),
    enabled: Boolean(selectedProgrammeId),
    staleTime: 3_000,
  });
  const selected =
    detailQuery.data?.status === "CLOSED" ? null : detailQuery.data;
  const optimizer = optimizerQuery.data;
  const readiness = readinessOf(selected, optimizer);
  const matrixPortfolio = useMemo(
    () =>
      matrixPortfolioQuery.data ||
      (selected
        ? [
            {
              programme: selected,
              scheduleLinks: scheduleLinksQuery.data?.items || [],
            },
          ]
        : []),
    [matrixPortfolioQuery.data, scheduleLinksQuery.data?.items, selected],
  );
  const matrixItems = useMemo(
    () =>
      matrixPortfolio.flatMap(({ programme }) =>
        (programme.items || []).filter((item) => item.state !== "CANCELLED"),
      ),
    [matrixPortfolio],
  );
  const matrixScheduleLinks = useMemo(
    () => matrixPortfolio.flatMap((entry) => entry.scheduleLinks),
    [matrixPortfolio],
  );
  const matrixProgrammeKindsById = useMemo(
    () =>
      new Map(
        matrixPortfolio.map(({ programme }) => [
          programme.id,
          programme.programme_kind || "INTERNAL",
        ]),
      ),
    [matrixPortfolio],
  );
  const editableProgrammeIds = useMemo(
    () =>
      new Set(
        canManage
          ? matrixPortfolio
              .filter(({ programme }) => programmeEditable(programme.status))
              .map(({ programme }) => programme.id)
          : [],
      ),
    [canManage, matrixPortfolio],
  );

  const [programmeForm, setProgrammeForm] = useState({
    programme_kind: "INTERNAL" as ProgrammeKind,
    title: programmeKindTitle("INTERNAL", currentYear),
    period_start: `${currentYear}-01-01`,
    period_end: `${currentYear}-12-31`,
    objectives: "Plan and complete the year's assurance audits.",
    regulatory_basis: "",
    copy_previous_year: false,
    rotate_auditors: false,
    apply_hybrid_seed: false,
  });
  const [itemForm, setItemForm] = useState({
    universe_item_id: "",
    audit_type: "PROCESS",
    title: "",
    purpose: "",
    scope: "",
    criteria: "",
    recurrence: "FIXED_DATES" as AuditProgrammeRecurrence,
    mandatory_surveillance: false,
    target_start: "",
    target_end: "",
    fixed_dates: [""],
    default_start_time: "09:00",
    default_end_time: "17:00",
    default_location: "",
    lead_auditor_user_id: "",
    observer_auditor_user_id: "",
    supporting_auditor_user_ids: [] as string[],
    auditee_user_id: "",
    notify_auditors: true,
    notify_auditees: true,
  });
  const [universeForm, setUniverseForm] = useState({
    entity_type: "DEPARTMENT" as AuditUniverseEntityType,
    programme_kind: "INTERNAL" as AuditUniverseProgrammeKind,
    aircraft_serial_number: "",
    display_label: "",
    risk_classification: "MEDIUM" as AuditRiskLevel,
    regulatory_criticality: "MEDIUM" as AuditRiskLevel,
    surveillance_interval_days: "365",
    mandatory_surveillance: false,
    notes: "",
  });
  const [editProgrammeForm, setEditProgrammeForm] = useState({
    title: "",
    period_start: "",
    period_end: "",
    objectives: "",
    regulatory_basis: "",
  });
  const [editItemForm, setEditItemForm] = useState({
    title: "",
    purpose: "",
    scope: "",
    criteria: "",
    recurrence: "ANNUAL" as AuditProgrammeRecurrence,
    mandatory_surveillance: false,
    target_start: "",
    target_end: "",
    fixed_dates: [""],
    default_start_time: "09:00",
    default_end_time: "17:00",
    default_location: "",
    lead_auditor_user_id: "",
    observer_auditor_user_id: "",
    supporting_auditor_user_ids: [] as string[],
    auditee_user_id: "",
    notify_auditors: true,
    notify_auditees: true,
  });
  const [editUniverseForm, setEditUniverseForm] = useState({
    programme_kind: "BOTH" as AuditUniverseProgrammeKind,
    display_label: "",
    source_route: "",
    risk_classification: "MEDIUM" as AuditRiskLevel,
    regulatory_criticality: "MEDIUM" as AuditRiskLevel,
    surveillance_interval_days: "",
    mandatory_surveillance: false,
    active: true,
    notes: "",
  });
  const aircraftQuery = useQuery({
    queryKey: ["qms-audit-universe-aircraft", amoCode],
    queryFn: () => listAircraft(),
    enabled:
      canManage &&
      showUniverseCreate &&
      universeForm.entity_type === "AIRCRAFT",
    staleTime: 10 * 60_000,
  });
  useEffect(() => {
    if (!standardAreasQuery.data) return;
    void queryClient.invalidateQueries({
      queryKey: ["qms-audit-universe", amoCode],
    });
    if (selectedProgrammeId) {
      void queryClient.invalidateQueries({
        queryKey: [
          "qms-audit-programme-optimizer",
          amoCode,
          selectedProgrammeId,
        ],
      });
    }
  }, [amoCode, queryClient, selectedProgrammeId, standardAreasQuery.data]);
  const [calendarMonthForm, setCalendarMonthForm] = useState({
    dates: [] as string[],
    default_start_time: "09:00",
    default_end_time: "17:00",
    default_location: "",
    lead_auditor_user_id: "",
    observer_auditor_user_id: "",
    supporting_auditor_user_ids: [] as string[],
    auditee_user_id: "",
    notify_auditors: true,
    notify_auditees: true,
  });

  const addItemAreaType = useMemo(() => {
    const universeId = itemForm.universe_item_id;
    if (!universeId) return null;
    return (
      (universeQuery.data?.items || []).find((item) => item.id === universeId)
        ?.entity_type || null
    );
  }, [itemForm.universe_item_id, universeQuery.data?.items]);

  const editItemAreaType =
    requirementFocus?.auditable_entity?.entity_type || null;

  const areaFieldSeeds = useMemo(() => {
    const collect = (entityType: string | null, field: "purpose" | "scope" | "criteria") => {
      if (!entityType) return [] as string[];
      const lines: string[] = [];
      for (const item of selected?.items || []) {
        if ((item.auditable_entity?.entity_type || "") !== entityType) continue;
        if (field === "purpose") {
          lines.push(...historyEntriesFromValue(item.purpose || ""));
        } else if (field === "scope") {
          lines.push(...historyEntriesFromValue(item.scope || ""));
        } else {
          lines.push(...historyEntriesFromValue(linesOf(item.criteria)));
        }
      }
      return lines;
    };
    return {
      addPurpose: collect(addItemAreaType, "purpose"),
      addScope: collect(addItemAreaType, "scope"),
      addCriteria: collect(addItemAreaType, "criteria"),
      editPurpose: collect(editItemAreaType, "purpose"),
      editScope: collect(editItemAreaType, "scope"),
      editCriteria: collect(editItemAreaType, "criteria"),
    };
  }, [addItemAreaType, editItemAreaType, selected?.items]);

  const purposeHistoryAdd = useTextFieldHistory(amoCode, "audit-purpose", {
    areaScope: fieldHistoryAreaFromEntity(addItemAreaType),
    enabled: Boolean(addItemAreaType),
    areaSeeds: areaFieldSeeds.addPurpose,
  });
  const scopeHistoryAdd = useTextFieldHistory(amoCode, "audit-scope", {
    areaScope: fieldHistoryAreaFromEntity(addItemAreaType),
    enabled: Boolean(addItemAreaType),
    areaSeeds: areaFieldSeeds.addScope,
  });
  const criteriaHistoryAdd = useTextFieldHistory(amoCode, "audit-criteria", {
    areaScope: fieldHistoryAreaFromEntity(addItemAreaType),
    enabled: Boolean(addItemAreaType),
    areaSeeds: areaFieldSeeds.addCriteria,
  });
  const purposeHistoryEdit = useTextFieldHistory(amoCode, "audit-purpose", {
    areaScope: fieldHistoryAreaFromEntity(editItemAreaType),
    enabled: Boolean(editItemAreaType),
    areaSeeds: areaFieldSeeds.editPurpose,
  });
  const scopeHistoryEdit = useTextFieldHistory(amoCode, "audit-scope", {
    areaScope: fieldHistoryAreaFromEntity(editItemAreaType),
    enabled: Boolean(editItemAreaType),
    areaSeeds: areaFieldSeeds.editScope,
  });
  const criteriaHistoryEdit = useTextFieldHistory(amoCode, "audit-criteria", {
    areaScope: fieldHistoryAreaFromEntity(editItemAreaType),
    enabled: Boolean(editItemAreaType),
    areaSeeds: areaFieldSeeds.editCriteria,
  });

  const openProgrammeEdit = (programme: AuditProgramme) => {
    setEditProgrammeForm({
      title: programme.title,
      period_start: programme.period_start,
      period_end: programme.period_end,
      objectives: linesOf(programme.objectives),
      regulatory_basis: linesOf(programme.regulatory_basis),
    });
    setEditReason("");
    setShowProgrammeEdit(true);
  };

  const openProgrammeCreate = (options?: { copyPreviousYear?: boolean }) => {
    const programme_kind = creatableKinds[0] || "INTERNAL";
    const copy_previous_year =
      options?.copyPreviousYear ??
      defaultCopyPreviousYear(priorYearProgrammes, programme_kind);
    setProgrammeForm({
      programme_kind,
      title: programmeKindTitle(programme_kind, year),
      period_start: `${year}-01-01`,
      period_end: `${year}-12-31`,
      objectives: "Plan and complete the year's assurance audits.",
      regulatory_basis: "",
      copy_previous_year,
      rotate_auditors: defaultRotateAuditors(copy_previous_year),
      apply_hybrid_seed: false,
    });
    setShowCreate(true);
  };

  const openUniverseCreate = () => {
    const targetKind =
      workspaceTab === "universe"
        ? areaKind
        : selected?.programme_kind === "INTERNAL"
          ? "INTERNAL"
          : "EXTERNAL";
    setUniverseForm((current) => ({
      ...current,
      entity_type: "DEPARTMENT",
      programme_kind: targetKind,
      aircraft_serial_number: "",
      display_label: "",
      notes: "",
    }));
    setShowUniverseCreate(true);
  };

  const openRequirementDrawer = (item: AuditProgrammeItem, edit: boolean) => {
    setCancelItemTarget(null);
    setAreaAuditsFocus(null);
    setRequirementFocus(item);
    setRequirementEditMode(edit);
    setEditItemForm({
      title: item.title,
      purpose: item.purpose || "",
      scope: item.scope || "",
      criteria: linesOf(item.criteria),
      recurrence: item.recurrence || "ANNUAL",
      mandatory_surveillance: item.mandatory_surveillance,
      target_start: item.target_start || "",
      target_end: item.target_end || "",
      fixed_dates: item.fixed_dates?.length
        ? item.fixed_dates.map(
            (value) => `${selected?.programme_year || year}-${value}`,
          )
        : [""],
      default_start_time: String(item.default_start_time || "09:00").slice(
        0,
        5,
      ),
      default_end_time: String(item.default_end_time || "17:00").slice(0, 5),
      default_location: item.default_location || "",
      lead_auditor_user_id: item.lead_auditor_user_id || "",
      observer_auditor_user_id: item.observer_auditor_user_id || "",
      supporting_auditor_user_ids: withoutLeadAuditor(
        item.supporting_auditor_user_ids || [],
        item.lead_auditor_user_id,
        item.observer_auditor_user_id,
      ),
      auditee_user_id: item.auditee_user_id || "",
      notify_auditors: item.notify_auditors !== false,
      notify_auditees: item.notify_auditees !== false,
    });
    setEditReason("");
  };

  const openRemoveAudit = (item: AuditProgrammeItem) => {
    setCalendarMonthTarget(null);
    setRequirementFocus(null);
    setRequirementEditMode(false);
    setAreaAuditsFocus(null);
    setCancelItemTarget(item);
    setCancelItemReason("Removed from draft programme");
  };

  const openCalendarMonth = (item: AuditProgrammeItem, month: number) => {
    const programmeYear = selected?.programme_year || year;
    const mode = auditMonthPlanningMode(item, month);
    const dates = (item.fixed_dates || [])
      .filter((value) => Number(value.slice(0, 2)) === month)
      .map((value) => `${programmeYear}-${value}`);
    setCalendarMonthForm({
      dates: dates.length ? dates : [programmeDate(programmeYear, month)],
      default_start_time: String(item.default_start_time || "09:00").slice(
        0,
        5,
      ),
      default_end_time: String(item.default_end_time || "17:00").slice(0, 5),
      default_location: item.default_location || "",
      lead_auditor_user_id: item.lead_auditor_user_id || "",
      observer_auditor_user_id: item.observer_auditor_user_id || "",
      supporting_auditor_user_ids: withoutLeadAuditor(
        item.supporting_auditor_user_ids || [],
        item.lead_auditor_user_id,
        item.observer_auditor_user_id,
      ),
      auditee_user_id: item.auditee_user_id || "",
      notify_auditors: item.notify_auditors !== false,
      notify_auditees: item.notify_auditees !== false,
    });
    setCalendarMonthTarget({ item, month, mode });
  };

  const openSeparateAuditFromCalendarMonth = () => {
    if (!calendarMonthTarget) return;
    const { item, month } = calendarMonthTarget;
    const programmeYear = selected?.programme_year || year;
    const monthLabel = new Date(2000, month - 1, 1).toLocaleString(
      undefined,
      { month: "long" },
    );
    setItemForm({
      universe_item_id: item.universe_item_id,
      audit_type: item.audit_type,
      title: `${item.title} · ${monthLabel}`,
      purpose: item.purpose || "",
      scope: item.scope,
      criteria: linesOf(item.criteria),
      recurrence: "FIXED_DATES",
      mandatory_surveillance: item.mandatory_surveillance,
      target_start: "",
      target_end: "",
      fixed_dates: calendarMonthForm.dates.length
        ? [...calendarMonthForm.dates]
        : [programmeDate(programmeYear, month)],
      default_start_time: calendarMonthForm.default_start_time,
      default_end_time: calendarMonthForm.default_end_time,
      default_location: calendarMonthForm.default_location,
      lead_auditor_user_id: calendarMonthForm.lead_auditor_user_id,
      observer_auditor_user_id: calendarMonthForm.observer_auditor_user_id,
      supporting_auditor_user_ids:
        calendarMonthForm.supporting_auditor_user_ids,
      auditee_user_id: calendarMonthForm.auditee_user_id,
      notify_auditors: calendarMonthForm.notify_auditors,
      notify_auditees: calendarMonthForm.notify_auditees,
    });
    setCalendarMonthTarget(null);
    setShowRequirement(true);
  };

  const startAuditFromMatrix = (area: AuditUniverseItem, month: number) => {
    const programmeYear = selected?.programme_year || year;
    setItemForm({
      universe_item_id: area.id,
      audit_type: auditTypeForEntity(area.entity_type),
      title: `${area.display_label} audit`,
      purpose: "",
      scope: area.display_label,
      criteria: "",
      recurrence: "FIXED_DATES",
      mandatory_surveillance: area.mandatory_surveillance,
      target_start: "",
      target_end: "",
      fixed_dates: [programmeDate(programmeYear, month)],
      default_start_time: "09:00",
      default_end_time: "17:00",
      default_location: suggestedLocationCode(area, locations),
      lead_auditor_user_id: "",
      observer_auditor_user_id: "",
      supporting_auditor_user_ids: [],
      auditee_user_id: "",
      notify_auditors: true,
      notify_auditees: true,
    });
    setShowRequirement(true);
  };

  const openUniverseDrawer = (item: AuditUniverseItem, edit: boolean) => {
    setUniverseFocus(item);
    setUniverseEditMode(edit);
    setEditUniverseForm({
      programme_kind: item.programme_kind || "BOTH",
      display_label: item.display_label,
      source_route: item.source_route || "",
      risk_classification: item.risk_classification,
      regulatory_criticality: item.regulatory_criticality,
      surveillance_interval_days:
        item.surveillance_interval_days != null
          ? String(item.surveillance_interval_days)
          : "",
      mandatory_surveillance: item.mandatory_surveillance,
      active: item.active,
      notes: item.notes || "",
    });
  };

  const invalidateProgramme = async (programmeId?: string) => {
    const id = programmeId || selectedProgrammeId;
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["qms-audit-programmes", amoCode],
      }),
      queryClient.invalidateQueries({
        queryKey: ["qms-audit-programme", amoCode, id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["qms-audit-programme-optimizer", amoCode, id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["qms-audit-programme-scheduling-queue", amoCode.trim().toLowerCase()],
      }),
      queryClient.invalidateQueries({
        queryKey: ["qms-audit-programme-schedule-links", amoCode, id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["qms-audit-programme-matrix-portfolio", amoCode],
      }),
    ]);
  };

  const createProgrammeMutation = useMutation({
    mutationFn: () =>
      createAuditProgramme(amoCode, {
        programme_year: year,
        programme_kind: programmeForm.programme_kind,
        title: programmeForm.title.trim(),
        objectives: programmeForm.objectives
          .split("\n")
          .map((value) => value.trim())
          .filter(Boolean),
        regulatory_basis: programmeForm.regulatory_basis
          .split("\n")
          .map((value) => value.trim())
          .filter(Boolean),
        period_start: programmeForm.period_start,
        period_end: programmeForm.period_end,
        copy_previous_year: programmeForm.copy_previous_year,
        rotate_auditors:
          programmeForm.copy_previous_year && programmeForm.rotate_auditors,
        apply_hybrid_seed: programmeForm.apply_hybrid_seed,
      }),
    onSuccess: async (programme) => {
      const carried = programmeForm.copy_previous_year;
      const rotated =
        programmeForm.copy_previous_year && programmeForm.rotate_auditors;
      const copiedCount = programme.items?.length ?? 0;
      objectivesHistory.remember(programmeForm.objectives);
      basisHistory.remember(programmeForm.regulatory_basis);
      setSelectedId(programme.id);
      setShowCreate(false);
      setWorkspaceTab("requirements");
      await invalidateProgramme(programme.id);
      if (carried) {
        const toast = carryForwardResultToast(
          copiedCount,
          year,
          priorYear,
          rotated,
        );
        pushToast({
          ...toast,
          dedupeKey: `audit-programme-create:${programme.id}`,
        });
      } else {
        pushToast({
          title: `${year} programme created`,
          message: "Blank draft ready — add audits from the programme matrix.",
          variant: "success",
          dedupeKey: `audit-programme-create:${programme.id}`,
        });
      }
    },
  });

  const updateProgrammeMutation = useMutation({
    mutationFn: () =>
      updateAuditProgramme(amoCode, selectedProgrammeId as string, {
        title: editProgrammeForm.title.trim(),
        objectives: editProgrammeForm.objectives
          .split("\n")
          .map((value) => value.trim())
          .filter(Boolean),
        regulatory_basis: editProgrammeForm.regulatory_basis
          .split("\n")
          .map((value) => value.trim())
          .filter(Boolean),
        period_start: editProgrammeForm.period_start,
        period_end: editProgrammeForm.period_end,
        reason: editReason.trim(),
      }),
    onSuccess: async (programme) => {
      objectivesHistory.remember(editProgrammeForm.objectives);
      basisHistory.remember(editProgrammeForm.regulatory_basis);
      setShowProgrammeEdit(false);
      setEditReason("");
      queryClient.setQueryData(
        ["qms-audit-programme", amoCode, programme.id],
        programme,
      );
      await invalidateProgramme(programme.id);
    },
  });

  const updateItemMutation = useMutation({
    mutationFn: () =>
      updateAuditProgrammeItem(
        amoCode,
        requirementFocus!.programme_id,
        requirementFocus!.id,
        {
          title: editItemForm.title.trim(),
          purpose: editItemForm.purpose.trim() || null,
          scope: editItemForm.scope.trim(),
          criteria: editItemForm.criteria
            .split("\n")
            .map((value) => value.trim())
            .filter(Boolean),
          recurrence: editItemForm.recurrence,
          mandatory_surveillance: editItemForm.mandatory_surveillance,
          target_start: editItemForm.target_start || null,
          target_end: editItemForm.target_end || null,
          fixed_dates: editItemForm.fixed_dates
            .filter(Boolean)
            .map((value) => value.slice(5)),
          default_start_time: editItemForm.default_start_time,
          default_end_time: editItemForm.default_end_time,
          default_duration_days:
            editItemForm.recurrence === "FIXED_DATES"
              ? requirementFocus?.default_duration_days || 1
              : workingDayCount(
                  editItemForm.target_start,
                  editItemForm.target_end,
                ),
          default_location: editItemForm.default_location.trim() || null,
          lead_auditor_user_id: editItemForm.lead_auditor_user_id || null,
          observer_auditor_user_id:
            editItemForm.observer_auditor_user_id || null,
          supporting_auditor_user_ids: withoutLeadAuditor(
            editItemForm.supporting_auditor_user_ids,
            editItemForm.lead_auditor_user_id,
            editItemForm.observer_auditor_user_id,
          ),
          auditee_user_id: editItemForm.auditee_user_id || null,
          notify_auditors: editItemForm.notify_auditors,
          notify_auditees: editItemForm.notify_auditees,
          auto_schedule: editItemForm.recurrence === "FIXED_DATES",
          reason: editReason.trim(),
        },
      ),
    onSuccess: async (item) => {
      purposeHistoryEdit.remember(editItemForm.purpose);
      scopeHistoryEdit.remember(editItemForm.scope);
      criteriaHistoryEdit.remember(editItemForm.criteria);
      setRequirementFocus(null);
      setRequirementEditMode(false);
      setEditReason("");
      await invalidateProgramme(item.programme_id);
    },
  });
  const calendarMonthMutation = useMutation({
    mutationFn: () => {
      if (!calendarMonthTarget)
        throw new Error("Select an audit month before saving.");
      const { item, month, mode } = calendarMonthTarget;
      const monthLabel = new Date(2000, month - 1, 1).toLocaleString(
        undefined,
        { month: "long" },
      );
      const datesOutsideMonth = (item.fixed_dates || []).filter(
        (value) => Number(value.slice(0, 2)) !== month,
      );
      const datesInMonth = calendarMonthForm.dates
        .filter(Boolean)
        .map((value) => value.slice(5));
      const fixedDates = [
        ...new Set([...datesOutsideMonth, ...datesInMonth]),
      ].sort();
      if (!fixedDates.length) {
        return updateAuditProgrammeItem(amoCode, item.programme_id, item.id, {
          state: "CANCELLED",
          cancellation_reason: `Removed from ${monthLabel} schedule`,
          reason: `Clear ${monthLabel} audit from the programme`,
        });
      }
      if (mode === "create") {
        return addAuditProgrammeItem(amoCode, item.programme_id, {
          universe_item_id: item.universe_item_id,
          audit_type: item.audit_type,
          title: `${item.title} · ${monthLabel}`,
          purpose: item.purpose || undefined,
          scope: item.scope,
          criteria: item.criteria || [],
          mandatory_surveillance: item.mandatory_surveillance,
          recurrence: "FIXED_DATES",
          fixed_dates: [...new Set(datesInMonth)].sort(),
          non_working_day_policy: "NEXT_WORKING_DAY",
          default_start_time: calendarMonthForm.default_start_time,
          default_end_time: calendarMonthForm.default_end_time,
          default_duration_days:
            item.default_duration_days ||
            workingDayCount(item.target_start, item.target_end),
          default_location:
            calendarMonthForm.default_location.trim() || undefined,
          lead_auditor_user_id:
            calendarMonthForm.lead_auditor_user_id || undefined,
          observer_auditor_user_id:
            calendarMonthForm.observer_auditor_user_id || undefined,
          supporting_auditor_user_ids: withoutLeadAuditor(
            calendarMonthForm.supporting_auditor_user_ids,
            calendarMonthForm.lead_auditor_user_id,
            calendarMonthForm.observer_auditor_user_id,
          ),
          auditee_user_id: calendarMonthForm.auditee_user_id || undefined,
          notify_auditors: calendarMonthForm.notify_auditors,
          notify_auditees: calendarMonthForm.notify_auditees,
          auto_schedule: true,
          prioritization_basis: [
            ...(item.prioritization_basis || []),
            {
              driver: "ADDITIONAL_PLANNED_OCCURRENCE",
              source_programme_item_id: item.id,
              month,
            },
          ],
        });
      }
      return updateAuditProgrammeItem(amoCode, item.programme_id, item.id, {
        recurrence: "FIXED_DATES",
        fixed_dates: fixedDates,
        target_start: null,
        target_end: null,
        non_working_day_policy: "NEXT_WORKING_DAY",
        default_start_time: calendarMonthForm.default_start_time,
        default_end_time: calendarMonthForm.default_end_time,
        default_duration_days:
          item.default_duration_days ||
          workingDayCount(item.target_start, item.target_end),
        default_location: calendarMonthForm.default_location.trim() || null,
        lead_auditor_user_id: calendarMonthForm.lead_auditor_user_id || null,
        observer_auditor_user_id:
          calendarMonthForm.observer_auditor_user_id || null,
        supporting_auditor_user_ids: withoutLeadAuditor(
          calendarMonthForm.supporting_auditor_user_ids,
          calendarMonthForm.lead_auditor_user_id,
          calendarMonthForm.observer_auditor_user_id,
        ),
        auditee_user_id: calendarMonthForm.auditee_user_id || null,
        notify_auditors: calendarMonthForm.notify_auditors,
        notify_auditees: calendarMonthForm.notify_auditees,
        auto_schedule: true,
        reason: `Annual programme date updated for ${monthLabel}.`,
      });
    },
    onSuccess: async (item) => {
      const created = calendarMonthTarget?.mode === "create";
      const removed = item.state === "CANCELLED";
      setCalendarMonthTarget(null);
      await invalidateProgramme(item.programme_id);
      pushToast({
        title: created
          ? "Additional audit created"
          : removed
            ? "Month audit removed"
            : "Audit dates updated",
        message: created
          ? "The existing audit was preserved and the additional month now has its own governed requirement."
          : removed
            ? "That month’s scheduled audit was removed from the draft programme."
            : "The audit series now includes the saved dates.",
        variant: "success",
        dedupeKey: `audit-programme-month:${item.id}`,
      });
    },
  });

  const cancelItemMutation = useMutation({
    mutationFn: (item: AuditProgrammeItem) =>
      updateAuditProgrammeItem(amoCode, item.programme_id, item.id, {
        state: "CANCELLED",
        cancellation_reason: cancelItemReason.trim() || "Removed from draft programme",
        reason: cancelItemReason.trim() || "Removed from draft programme",
      }),
    onSuccess: async (item) => {
      setRequirementFocus(null);
      setRequirementEditMode(false);
      setAreaAuditsFocus(null);
      setCancelItemTarget(null);
      setCancelItemReason("");
      await invalidateProgramme(item.programme_id);
      pushToast({
        title: "Audit removed",
        message: `${item.title} was removed from this draft programme.`,
        variant: "success",
        dedupeKey: `audit-programme-remove:${item.id}`,
      });
    },
  });

  const updateUniverseMutation = useMutation({
    mutationFn: () =>
      updateAuditUniverseItem(amoCode, universeFocus!.id, {
        programme_kind: editUniverseForm.programme_kind,
        display_label: editUniverseForm.display_label.trim(),
        source_route: editUniverseForm.source_route.trim() || null,
        risk_classification: editUniverseForm.risk_classification,
        regulatory_criticality: editUniverseForm.regulatory_criticality,
        surveillance_interval_days: editUniverseForm.surveillance_interval_days
          ? Number(editUniverseForm.surveillance_interval_days)
          : null,
        mandatory_surveillance: editUniverseForm.mandatory_surveillance,
        active: editUniverseForm.active,
        notes: editUniverseForm.notes.trim() || null,
      }),
    onSuccess: async () => {
      setUniverseFocus(null);
      setUniverseEditMode(false);
      await queryClient.invalidateQueries({
        queryKey: ["qms-audit-universe", amoCode],
      });
      await invalidateProgramme();
    },
  });

  const removeUniverseMutation = useMutation({
    mutationFn: () =>
      updateAuditUniverseItem(amoCode, removeUniverseTarget!.id, {
        active: false,
      }),
    onSuccess: async () => {
      setRemoveUniverseTarget(null);
      setUniverseFocus(null);
      setUniverseEditMode(false);
      await queryClient.invalidateQueries({
        queryKey: ["qms-audit-universe", amoCode],
      });
      await invalidateProgramme();
    },
  });

  const optimizerMutation = useMutation({
    mutationFn: () =>
      rebuildAuditProgrammeOptimizer(amoCode, selectedProgrammeId as string),
    onSuccess: async (result) => {
      queryClient.setQueryData(
        ["qms-audit-programme-optimizer", amoCode, selectedProgrammeId],
        result,
      );
      await invalidateProgramme();
    },
  });

  const transitionMutation = useMutation({
    mutationFn: ({
      target,
      reason,
    }: {
      target: AuditProgrammeStatus;
      reason: string;
    }) =>
      transitionAuditProgramme(
        amoCode,
        selectedProgrammeId as string,
        target,
        reason.trim(),
      ),
    onSuccess: async (programme) => {
      setActionReason("");
      setDiscardReason("");
      setShowDiscardConfirm(false);
      setActionFeedback(
        programme.status === "UNDER_REVIEW"
          ? "Submitted. The Quality Manager has been notified and the revision is now frozen."
          : programme.status === "APPROVED"
            ? "Accountable Executive approval recorded. The controlled schedule is ready to download and publish."
            : programme.status === "ACTIVE"
              ? "Published. Fixed-date schedules were generated and the audit team and auditees were notified according to each requirement."
              : programme.status === "DRAFT"
                ? "Returned to draft for correction. The programme owner has been notified."
                : programme.status === "CLOSED"
                  ? "Draft programme discarded and closed."
                  : `Programme moved to ${human(programme.status)}.`,
      );
      if (programme.status === "CLOSED") {
        const closedId = programme.id;
        setSelectedId(null);
        setShowProgrammeDetail(false);
        setWorkspaceTab("requirements");
        const next = new URLSearchParams(searchParams);
        next.delete("programme");
        next.delete("tab");
        setSearchParams(next, { replace: true });
        queryClient.removeQueries({
          queryKey: ["qms-audit-programme", amoCode, closedId],
        });
        queryClient.removeQueries({
          queryKey: ["qms-audit-programme-optimizer", amoCode, closedId],
        });
        queryClient.setQueryData<AuditProgrammeList>(
          ["qms-audit-programmes", amoCode, year],
          (current) =>
            current
              ? {
                  ...current,
                  items: current.items.map((item) =>
                    item.id === closedId ? programme : item,
                  ),
                }
              : current,
        );
        await invalidateProgramme(closedId);
        pushToast({
          title: "Draft discarded",
          message: "The year is free to create a new programme.",
          variant: "success",
          dedupeKey: `audit-programme-discard:${closedId}`,
        });
        return;
      }
      queryClient.setQueryData(
        ["qms-audit-programme", amoCode, programme.id],
        programme,
      );
      queryClient.setQueryData<AuditProgrammeList>(
        ["qms-audit-programmes", amoCode, year],
        (current) =>
          current
            ? {
                ...current,
                items: current.items.map((item) =>
                  item.id === programme.id ? programme : item,
                ),
              }
            : current,
      );
      await invalidateProgramme(programme.id);
    },
  });

  const qualityReviewMutation = useMutation({
    mutationFn: (decision: "FORWARD" | "RETURN") =>
      reviewAuditProgramme(
        amoCode,
        selectedProgrammeId as string,
        decision,
        actionReason.trim(),
      ),
    onSuccess: async (programme) => {
      setActionReason("");
      setActionFeedback(
        programme.quality_reviewed_at
          ? "Quality Manager review recorded. The Accountable Executive has been notified for final approval."
          : "Returned to draft. The preparer and programme owner have been notified.",
      );
      queryClient.setQueryData(
        ["qms-audit-programme", amoCode, programme.id],
        programme,
      );
      await invalidateProgramme(programme.id);
    },
  });

  const amendmentMutation = useMutation({
    mutationFn: () =>
      createAuditProgrammeAmendment(
        amoCode,
        selectedProgrammeId as string,
        actionReason.trim(),
      ),
    onSuccess: async (programme) => {
      setSelectedId(programme.id);
      setActionReason("");
      await invalidateProgramme(programme.id);
    },
  });

  const itemMutation = useMutation({
    mutationFn: () => {
      const selectedArea = programmeUniverseItems.find(
        (area) => area.id === itemForm.universe_item_id,
      );
      return addAuditProgrammeItem(amoCode, selectedProgrammeId as string, {
        universe_item_id: itemForm.universe_item_id,
        audit_type: auditTypeForEntity(selectedArea?.entity_type),
        title: itemForm.title.trim(),
        purpose: itemForm.purpose.trim() || undefined,
        scope: itemForm.scope.trim(),
        criteria: itemForm.criteria
          .split("\n")
          .map((value) => value.trim())
          .filter(Boolean),
        mandatory_surveillance: itemForm.mandatory_surveillance,
        recurrence: itemForm.recurrence,
        target_start: itemForm.target_start || undefined,
        target_end: itemForm.target_end || undefined,
        fixed_dates: itemForm.fixed_dates
          .filter(Boolean)
          .map((value) => value.slice(5)),
        default_start_time: itemForm.default_start_time,
        default_end_time: itemForm.default_end_time,
        default_duration_days:
          itemForm.recurrence === "FIXED_DATES"
            ? 1
            : workingDayCount(itemForm.target_start, itemForm.target_end),
        default_location: itemForm.default_location.trim() || undefined,
        lead_auditor_user_id: itemForm.lead_auditor_user_id || undefined,
        observer_auditor_user_id:
          itemForm.observer_auditor_user_id || undefined,
        supporting_auditor_user_ids: withoutLeadAuditor(
          itemForm.supporting_auditor_user_ids,
          itemForm.lead_auditor_user_id,
          itemForm.observer_auditor_user_id,
        ),
        auditee_user_id: itemForm.auditee_user_id || undefined,
        notify_auditors: itemForm.notify_auditors,
        notify_auditees: itemForm.notify_auditees,
        auto_schedule: itemForm.recurrence === "FIXED_DATES",
        prioritization_basis: [
          { driver: "PROCESS_IMPORTANCE", source: "HUMAN_ADDITION" },
        ],
      });
    },
    onSuccess: async () => {
      purposeHistoryAdd.remember(itemForm.purpose);
      scopeHistoryAdd.remember(itemForm.scope);
      criteriaHistoryAdd.remember(itemForm.criteria);
      setShowRequirement(false);
      setItemForm((current) => ({
        ...current,
        title: "",
        purpose: "",
        scope: "",
        criteria: "",
        target_start: "",
        target_end: "",
        fixed_dates: [""],
        observer_auditor_user_id: "",
        supporting_auditor_user_ids: [],
      }));
      await invalidateProgramme();
    },
  });

  const universeMutation = useMutation({
    mutationFn: () => {
      const selectedAircraft: AircraftRead | undefined =
        aircraftQuery.data?.find(
          (aircraft) =>
            aircraft.serial_number === universeForm.aircraft_serial_number,
        );
      const aircraftModel =
        selectedAircraft?.model ||
        selectedAircraft?.aircraft_model_code ||
        "Model not recorded";
      const label =
        universeForm.entity_type === "AIRCRAFT"
          ? `${selectedAircraft?.registration || "Aircraft"} · ${aircraftModel}`
          : universeForm.display_label.trim();
      const sourceId =
        (universeForm.entity_type === "AIRCRAFT"
          ? universeForm.aircraft_serial_number
          : "") ||
        label
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-+|-+$/g, "") ||
        "coverage-area";
      return createAuditUniverseItem(amoCode, {
        entity_type: universeForm.entity_type,
        programme_kind: universeForm.programme_kind,
        display_label: label,
        source_owner_module:
          universeForm.entity_type === "AIRCRAFT" ? "FLEET" : "AUDIT_PROGRAMME",
        source_type:
          universeForm.entity_type === "AIRCRAFT"
            ? "AIRCRAFT"
            : universeForm.entity_type,
        source_id: sourceId,
        source_route:
          universeForm.entity_type === "AIRCRAFT"
            ? `/maintenance/${encodeURIComponent(amoCode)}/production/fleet/${encodeURIComponent(sourceId)}`
            : undefined,
        risk_classification: universeForm.risk_classification,
        regulatory_criticality: universeForm.regulatory_criticality,
        surveillance_interval_days: universeForm.surveillance_interval_days
          ? Number(universeForm.surveillance_interval_days)
          : undefined,
        mandatory_surveillance: universeForm.mandatory_surveillance,
        notes: universeForm.notes.trim() || undefined,
      });
    },
    onSuccess: async (item) => {
      await queryClient.invalidateQueries({
        queryKey: ["qms-audit-universe", amoCode],
      });
      setItemForm((current) => ({ ...current, universe_item_id: item.id }));
      setShowUniverseCreate(false);
      // Do not auto-rebuild the hybrid optimizer here — that silently seeded
      // unexplained audits into blank drafts. User can run Rebuild recommendations explicitly.
    },
  });

  const linksByItem = useMemo(
    () =>
      new Map(
        matrixScheduleLinks.map((link) => [link.programme_item_id, link]),
      ),
    [matrixScheduleLinks],
  );
  const queue = (queueQuery.data?.items || []).filter(
    (item) => !selectedProgrammeId || item.programme_id === selectedProgrammeId,
  );
  const people = peopleQuery.data?.people || [];
  const locations = peopleQuery.data?.locations || [];
  const auditorOptions = people.filter((person) => (person.auditor_roles || []).length > 0);
  const leadAuditorOptions = programmeLeadAuditorOptions(people);
  const leadOptionsAreFallbackAuditors =
    leadAuditorOptions.length > 0 &&
    !leadAuditorOptions.some((person) =>
      (person.auditor_roles || []).includes("LEAD_AUDITOR"),
    );
  const auditorNames = useMemo(
    () =>
      new Map(
        (peopleQuery.data?.people || []).map((person) => [
          person.id,
          person.full_name,
        ]),
      ),
    [peopleQuery.data?.people],
  );
  const error =
    programmesQuery.error ||
    universeQuery.error ||
    standardAreasQuery.error ||
    aircraftQuery.error ||
    peopleQuery.error ||
    queueQuery.error ||
    matrixPortfolioQuery.error ||
    detailQuery.error ||
    optimizerQuery.error ||
    scheduleLinksQuery.error ||
    createProgrammeMutation.error ||
    updateProgrammeMutation.error ||
    updateItemMutation.error ||
    calendarMonthMutation.error ||
    cancelItemMutation.error ||
    updateUniverseMutation.error ||
    removeUniverseMutation.error ||
    optimizerMutation.error ||
    transitionMutation.error ||
    qualityReviewMutation.error ||
    amendmentMutation.error ||
    itemMutation.error ||
    universeMutation.error;

  useEffect(() => {
    if (!error) return;
    const message =
      error instanceof Error
        ? error.message
        : "The audit programme action could not be completed.";
    pushToast({
      title: "Audit programme action failed",
      message,
      variant: "error",
      dedupeKey: `audit-programme-error:${message}`,
    });
  }, [error, pushToast]);

  const openSchedule = (programmeId: string, itemId: string) => {
    if (!canManage) return;
    setScheduleTarget({ programmeId, itemId });
  };

  const downloadSchedule = async (format: "pdf" | "ics") => {
    if (!selected) return;
    setDownloadBusy(format);
    setActionFeedback(null);
    try {
      await downloadAuditProgrammeSchedule(
        amoCode,
        selected.id,
        selected.programme_ref,
        format,
      );
      setActionFeedback(
        format === "pdf"
          ? programmeIsControlled(selected)
            ? "Controlled programme PDF downloaded."
            : "Draft programme PDF downloaded."
          : "Calendar snapshot downloaded. Use Sync calendar for automatic updates.",
      );
    } catch (reason) {
      setActionFeedback(
        reason instanceof Error ? reason.message : "The schedule could not be downloaded.",
      );
    } finally {
      setDownloadBusy(null);
    }
  };

  const selectedModel = normalizeAssuranceModel(selected?.assurance_model);
  const tabs: Array<{ id: WorkspaceTab; label: string }> = [
    { id: "requirements", label: "Programme" },
    { id: "universe", label: "Audit areas" },
    { id: "readiness", label: "Approval" },
  ];
  const approvalStage = selected ? programmeApprovalStage(selected) : null;
  const linkedRequirementCount = (universeItemId: string) =>
    (selected?.items || []).filter(
      (item) => item.universe_item_id === universeItemId,
    ).length;
  const unscheduledItems = (selected?.items || []).filter(
    (item) =>
      item.state === "PLANNED" &&
      !(item.recurrence === "FIXED_DATES" && item.auto_schedule),
  );
  const autoPublishItems = (selected?.items || []).filter(
    (item) => item.state === "PLANNED" && item.recurrence === "FIXED_DATES" && item.auto_schedule,
  );
  const auditorNoticeCount = (selected?.items || []).filter((item) => item.notify_auditors).length;
  const auditeeNoticeCount = (selected?.items || []).filter((item) => item.notify_auditees).length;
  const visibleUniverseItems = useMemo(
    () =>
      (universeQuery.data?.items || []).filter(
        (item) =>
          ((item.programme_kind || "BOTH") === areaKind ||
            (item.programme_kind || "BOTH") === "BOTH") &&
          (showInactiveAreas || item.active),
      ),
    [areaKind, showInactiveAreas, universeQuery.data?.items],
  );
  const selectedProgrammeKind =
    selected?.programme_kind || selectedProgrammeSummary?.programme_kind;
  const programmeKind =
    selectedProgrammeKind === "INTERNAL" ? "INTERNAL" : "EXTERNAL";
  const programmeUniverseItems = (universeQuery.data?.items || []).filter(
    (item) => {
      const itemKind = item.programme_kind || "BOTH";
      return itemKind === "BOTH" || itemKind === programmeKind;
    },
  );
  const selectedProgrammeView: AuditKindView =
    selectedProgrammeKind === "INTERNAL" ? "INTERNAL" : "EXTERNAL";
  const matrixEditable =
    auditKindView !== "BOTH" &&
    auditKindView === selectedProgrammeView &&
    Boolean(selectedProgrammeId) &&
    editableProgrammeIds.has(selectedProgrammeId as string);
  const changeAuditKindView = (nextView: AuditKindView) => {
    setAuditKindView(nextView);
    if (nextView === "BOTH") return;
    const target = visibleProgrammes.find((candidate) => {
      const kind = programmeKindOf(candidate);
      return nextView === "INTERNAL"
        ? kind === "INTERNAL"
        : kind === "EXTERNAL" || kind === "THIRD_PARTY";
    });
    if (target) setSelectedId(target.id);
  };
  const aircraftForArea = aircraftQuery.data?.find(
    (aircraft) =>
      aircraft.serial_number === universeForm.aircraft_serial_number,
  );
  const universeGridContext: AuditAreaGridContext = {
    canManage,
    selected,
    selectedProgrammeId,
    linkedRequirementCount,
    open: openUniverseDrawer,
    remove: setRemoveUniverseTarget,
    schedule: (data) => {
      setItemForm((form) => ({
        ...form,
        universe_item_id: data.id,
        audit_type: auditTypeForEntity(data.entity_type),
        title: `${data.display_label} audit`,
        scope: data.display_label,
        default_location:
          form.default_location || suggestedLocationCode(data, locations),
        mandatory_surveillance: data.mandatory_surveillance,
      }));
      setShowRequirement(true);
    },
  };

  return (
    <div
      className="qms-audit-programme qms-audit-programme-flow"
      aria-label="Audit Programme workspace"
    >
      <nav
        className="qms-audit-programme-flow__tabs"
        aria-label="Programme workspace sections"
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={workspaceTab === tab.id ? "is-active" : ""}
            aria-current={workspaceTab === tab.id ? "page" : undefined}
            onClick={() => {
              setWorkspaceTab(tab.id);
              const next = new URLSearchParams(searchParams);
              if (tab.id === "readiness") next.set("tab", "approval");
              else next.delete("tab");
              if (selectedProgrammeId) next.set("programme", selectedProgrammeId);
              setSearchParams(next, { replace: true });
              if (tab.id === "universe" && selected?.programme_kind) {
                setAreaKind(
                  selected?.programme_kind === "INTERNAL"
                    ? "INTERNAL"
                    : "EXTERNAL",
                );
              }
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {error ? (
        <div className="qms-audit-programme__error" role="alert">
          <AlertTriangle size={16} />{" "}
          {error instanceof Error
            ? error.message
            : "Audit programme data could not be loaded."}
        </div>
      ) : null}

      {(workspaceTab === "requirements" || workspaceTab === "readiness") &&
      !programmesQuery.isLoading &&
      !visibleProgrammes.length ? (
        <div
          className="qms-audit-programme-flow__empty qms-audit-programme-flow__empty--portfolio"
          role="status"
        >
          <div>
            <strong>No programme for {year}</strong>
            <p>
              {emptyYearCreateHint(year, priorYear, canCarryForwardDefaultKind)}
            </p>
          </div>
          {allowCreateProgramme ? (
            <button
              type="button"
              className="is-primary"
              onClick={() =>
                openProgrammeCreate({
                  copyPreviousYear: canCarryForwardDefaultKind,
                })
              }
            >
              <Plus size={15} />{" "}
              {emptyYearCreateLabel(
                year,
                priorYear,
                canCarryForwardDefaultKind,
              )}
            </button>
          ) : canManage ? (
            <small>
              An active programme already exists for {year}. Amend it or close
              it before creating another.
            </small>
          ) : (
            <small>
              Audit manage permission is required to create a programme.
            </small>
          )}
        </div>
      ) : (
        <div className="qms-audit-programme__workspace qms-audit-programme-flow__workspace qms-audit-programme-flow__workspace--single">
          <section className="qms-audit-programme__detail">
            {workspaceTab !== "requirements" && visibleProgrammes.length ? (
              <div className="qms-audit-programme-flow__programme-selector">
                <label>
                  <span>Programme</span>
                  <select
                    value={selectedProgrammeId || ""}
                    onChange={(event) => {
                      const programmeId = event.target.value;
                      const programme = visibleProgrammes.find(
                        (entry) => entry.id === programmeId,
                      );
                      setSelectedId(programmeId);
                      const next = new URLSearchParams(searchParams);
                      next.set("programme", programmeId);
                      if (workspaceTab === "readiness") next.set("tab", "approval");
                      setSearchParams(next, { replace: true });
                      if (programme)
                        setAreaKind(
                          programme.programme_kind === "INTERNAL"
                            ? "INTERNAL"
                            : "EXTERNAL",
                        );
                    }}
                  >
                    {visibleProgrammes.map((programme) => (
                      <option key={programme.id} value={programme.id}>
                        {programmeDisplayLabel(programme)} ·{" "}
                        {human(programme.status)}
                      </option>
                    ))}
                  </select>
                </label>
                {selected ? (
                  <b
                    className={`qms-chip qms-chip--${statusTone(selected.status)}`}
                  >
                    {human(selected.status)}
                  </b>
                ) : null}
              </div>
            ) : null}
            {workspaceTab === "universe" ? (
              <section
                className="qms-audit-programme-flow__coverage-panel"
                aria-labelledby="qms-audit-universe-heading"
              >
                <header className="qms-audit-programme-flow__coverage-header">
                  <div>
                    <h2 id="qms-audit-universe-heading">
                      <Library size={14} /> Audit area catalogue
                    </h2>
                    <p>
                      {selected ? (
                        <>
                          Choose the rows audited by{" "}
                          <strong>{programmeDisplayLabel(selected)}</strong>.
                          Use the schedule action to place a row in the 12-month
                          programme.
                        </>
                      ) : (
                        <>
                          Choose auditable departments, processes, facilities,
                          providers, or aircraft, then schedule them in a
                          programme.
                        </>
                      )}
                    </p>
                  </div>
                  {canManage ? (
                    <button
                      type="button"
                      className="is-primary"
                      onClick={openUniverseCreate}
                    >
                      <Plus size={14} /> Add tenant area
                    </button>
                  ) : null}
                </header>
                <div
                  className="qms-audit-area-linkage"
                  aria-label="Audit area programme linkage"
                >
                  <span>
                    <b>1</b> Select an audit area
                  </span>
                  <ArrowRight size={14} aria-hidden="true" />
                  <span>
                    <b>2</b> Add it to this programme
                  </span>
                  <ArrowRight size={14} aria-hidden="true" />
                  <span>
                    <b>3</b> Set its month and date
                  </span>
                </div>
                <div className="qms-audit-area-toolbar">
                  <div
                    className="qms-audit-area-kind"
                    role="group"
                    aria-label="Audit area type"
                  >
                    <button
                      type="button"
                      className={areaKind === "INTERNAL" ? "is-active" : ""}
                      aria-pressed={areaKind === "INTERNAL"}
                      onClick={() => setAreaKind("INTERNAL")}
                    >
                      Internal audit areas
                    </button>
                    <button
                      type="button"
                      className={areaKind === "EXTERNAL" ? "is-active" : ""}
                      aria-pressed={areaKind === "EXTERNAL"}
                      onClick={() => setAreaKind("EXTERNAL")}
                    >
                      External audit areas
                    </button>
                  </div>
                  <label className="qms-audit-area-toolbar__removed">
                    <input
                      type="checkbox"
                      checked={showInactiveAreas}
                      onChange={(event) =>
                        setShowInactiveAreas(event.target.checked)
                      }
                    />
                    <span>Show removed</span>
                  </label>
                </div>
                {universeQuery.isLoading || standardAreasQuery.isLoading ? (
                  <p className="qms-audit-programme-flow__empty">
                    Loading audit areas…
                  </p>
                ) : !visibleUniverseItems.length ? (
                  <div className="qms-audit-programme-flow__empty qms-audit-programme-flow__empty--portfolio">
                    <div>
                      <strong>
                        No {areaKind.toLowerCase()} audit areas in this view
                      </strong>
                      <p>
                        Standard areas are tenant-local copies. Add a
                        tenant-specific area when your approval or operation
                        needs another row.
                      </p>
                    </div>
                    {canManage ? (
                      <button
                        type="button"
                        className="is-primary"
                        onClick={openUniverseCreate}
                      >
                        <Plus size={14} /> Add tenant area
                      </button>
                    ) : null}
                  </div>
                ) : (
                  <div className="qms-programme-grid ag-theme-alpine">
                    <AgGridReact<AuditUniverseItem>
                      key={`audit-areas:${selectedProgrammeId || "none"}:${areaKind}`}
                      rowData={visibleUniverseItems}
                      columnDefs={AUDIT_AREA_COLUMNS}
                      context={universeGridContext}
                      defaultColDef={AUDIT_AREA_DEFAULT_COL_DEF}
                      getRowId={getAuditAreaRowId}
                      rowHeight={52}
                      headerHeight={34}
                      domLayout="autoHeight"
                      animateRows={false}
                      suppressCellFocus
                    />
                  </div>
                )}
              </section>
            ) : !selectedProgrammeId ? (
              <div className="qms-audit-programme-flow__empty qms-audit-programme-flow__empty--inline">
                <p>Select a programme revision.</p>
              </div>
            ) : detailQuery.isLoading ? (
              <p className="qms-audit-programme-flow__empty">
                Loading programme…
              </p>
            ) : !selected ? (
              <p className="qms-audit-programme-flow__empty">
                Programme not available.
              </p>
            ) : (
              <>
                {workspaceTab === "readiness" ? (
                  <header className="qms-audit-programme-flow__detail-toolbar">
                    <div>
                      <h2>Approval & publication</h2>
                      <small>Three governed roles, one frozen revision, then controlled distribution.</small>
                    </div>
                    <div className="qms-audit-programme-flow__detail-actions">
                      {selected && canExport ? (
                        <button type="button" className="is-secondary" disabled={Boolean(downloadBusy)} onClick={() => void downloadSchedule("pdf")}>
                          <Download size={14} /> {downloadBusy === "pdf" ? "Preparing…" : programmeIsControlled(selected) ? "Download PDF" : "Download draft PDF"}
                        </button>
                      ) : null}
                      {selected && programmeIsControlled(selected) && canExport ? (
                        <button type="button" className="is-secondary" disabled={Boolean(downloadBusy)} onClick={() => void downloadSchedule("ics")}>
                          <Download size={14} /> Calendar snapshot
                        </button>
                      ) : null}
                      <button type="button" className="is-secondary" onClick={() => setCalendarSyncOpen(true)}>
                        <CalendarCheck2 size={14} /> Sync calendar
                      </button>
                      <button
                        type="button"
                        className="is-secondary"
                        onClick={() => setShowProgrammeDetail(true)}
                      >
                        Programme details
                      </button>
                    </div>
                  </header>
                ) : null}

                {workspaceTab === "requirements" ? (
                  <>
                    <QmsAuditProgrammeMatrix
                      programme={selected}
                      programmes={visibleProgrammes}
                      year={year}
                      items={matrixItems}
                      coverageAreas={universeQuery.data?.items || []}
                      scheduleLinks={matrixScheduleLinks}
                      auditorNames={auditorNames}
                      programmeKindsById={matrixProgrammeKindsById}
                      editableProgrammeIds={editableProgrammeIds}
                      auditKindView={auditKindView}
                      editable={matrixEditable}
                      canSchedule={canManage}
                      loading={
                        universeQuery.isLoading ||
                        matrixPortfolioQuery.isLoading
                      }
                      refreshing={
                        programmesQuery.isFetching ||
                        universeQuery.isFetching ||
                        queueQuery.isFetching ||
                        optimizerQuery.isFetching
                      }
                      onProgrammeChange={(programmeId) => {
                        setSelectedId(programmeId);
                        if (auditKindView === "BOTH") return;
                        const target = visibleProgrammes.find(
                          (candidate) => candidate.id === programmeId,
                        );
                        const kind = target ? programmeKindOf(target) : null;
                        setAuditKindView(
                          kind === "INTERNAL" ? "INTERNAL" : "EXTERNAL",
                        );
                      }}
                      onAuditKindViewChange={changeAuditKindView}
                      onYearChange={(nextYear) => {
                        setSelectedId(null);
                        setYear(nextYear);
                      }}
                      onRefresh={() => {
                        void programmesQuery.refetch();
                        void universeQuery.refetch();
                        void queueQuery.refetch();
                        void optimizerQuery.refetch();
                        void scheduleLinksQuery.refetch();
                        void matrixPortfolioQuery.refetch();
                      }}
                      onHowItWorks={() => setShowMethodologyInfo(true)}
                      calendarHref={plannerHref}
                      onEditProgramme={
                        canManage && programmeEditable(selected.status)
                          ? () => openProgrammeEdit(selected)
                          : undefined
                      }
                      onNewProgramme={
                        allowCreateProgramme ? openProgrammeCreate : undefined
                      }
                      onDiscardProgramme={
                        canManage && selected.status === "DRAFT"
                          ? () => {
                              setDiscardReason("");
                              setShowDiscardConfirm(true);
                            }
                          : undefined
                      }
                      onDownloadPdf={
                        canExport
                          ? () => void downloadSchedule("pdf")
                          : undefined
                      }
                      downloadBusy={Boolean(downloadBusy)}
                      onAddAudit={() => setShowRequirement(true)}
                      onAddCoverageArea={openUniverseCreate}
                      onAddAreaMonth={startAuditFromMatrix}
                      onEditMonth={(item, month) => {
                        setSelectedId(item.programme_id);
                        openCalendarMonth(item, month);
                      }}
                      onViewItem={(item) => {
                        setSelectedId(item.programme_id);
                        openRequirementDrawer(item, false);
                      }}
                      onViewArea={(items, areaLabel) => {
                        const unique = Array.from(
                          new Map(items.map((item) => [item.id, item])).values(),
                        );
                        if (unique.length === 1) {
                          setSelectedId(unique[0].programme_id);
                          openRequirementDrawer(unique[0], false);
                          return;
                        }
                        setSelectedId(unique[0]?.programme_id || selectedId);
                        setRequirementFocus(null);
                        setRequirementEditMode(false);
                        setAreaAuditsFocus({
                          areaLabel,
                          items: unique,
                        });
                      }}
                      onEditItem={(item) => {
                        setSelectedId(item.programme_id);
                        openRequirementDrawer(item, true);
                      }}
                      onScheduleItem={(item) =>
                        openSchedule(item.programme_id, item.id)
                      }
                    />

                    {queue.length ? (
                      <section
                        className="qms-audit-programme-flow__queue qms-audit-programme-flow__queue--compact"
                        aria-label="Programme scheduling queue"
                      >
                        <header>
                          <div>
                            <strong>
                              <CalendarClock size={16} /> Needs scheduling
                            </strong>
                            <small>
                              {queue.length} approved audit
                              {queue.length === 1 ? "" : "s"} waiting for a
                              calendar date.
                            </small>
                          </div>
                          <Link to={plannerHref}>
                            Open Calendar <ArrowRight size={14} />
                          </Link>
                        </header>
                        <div>
                          {queue.slice(0, 6).map((item) =>
                            SCHEDULABLE_RECURRENCES.has(item.recurrence) &&
                            canManage ? (
                              <button
                                key={item.programme_item_id}
                                type="button"
                                onClick={() =>
                                  openSchedule(
                                    item.programme_id,
                                    item.programme_item_id,
                                  )
                                }
                                title={item.title}
                              >
                                <span>
                                  <strong title={item.title}>
                                    {item.title}
                                  </strong>
                                  <small>
                                    {dateLabel(item.target_start)} →{" "}
                                    {dateLabel(item.target_end)} ·{" "}
                                    {human(item.recurrence)}
                                  </small>
                                </span>
                                <CalendarClock size={16} />
                              </button>
                            ) : (
                              <span
                                key={item.programme_item_id}
                                title={item.title}
                              >
                                <strong title={item.title}>{item.title}</strong>
                                <small>{human(item.recurrence)}</small>
                              </span>
                            ),
                          )}
                        </div>
                      </section>
                    ) : null}
                  </>
                ) : null}

                {workspaceTab === "readiness" ? (
                  <>
                    <section className="qms-audit-programme-flow__approval-route" aria-label="Programme approval route">
                      <article className={`${approvalStage === "PREPARATION" ? "is-current" : ""}${selected.submitted_at || selected.status !== "DRAFT" ? " is-complete" : ""}`}>
                        <span><Send size={17} /></span>
                        <div><small>1 · Quality Officer</small><strong>Prepare & submit</strong><p>Build scope, criteria, dates, team and distribution. May submit and publish; cannot review or approve.</p></div>
                        <b>{selected.submitted_at ? "Submitted" : approvalStage === "PREPARATION" ? "Current" : "Pending"}</b>
                      </article>
                      <article className={`${approvalStage === "QUALITY_REVIEW" ? "is-current" : ""}${selected.quality_reviewed_at ? " is-complete" : ""}`}>
                        <span><UserCheck size={17} /></span>
                        <div><small>2 · Quality Manager</small><strong>Independent quality review</strong><p>Checks regulatory coverage, risk logic and audit independence. May return or forward; cannot give final approval.</p></div>
                        <b>{selected.quality_reviewed_at ? "Reviewed" : approvalStage === "QUALITY_REVIEW" ? "Current" : "Pending"}</b>
                      </article>
                      <article className={`${approvalStage === "EXECUTIVE_APPROVAL" ? "is-current" : ""}${selected.approved_at ? " is-complete" : ""}`}>
                        <span><FileCheck2 size={17} /></span>
                        <div><small>3 · Accountable Executive</small><strong>Final approval</strong><p>Accepts accountability and resources for the frozen revision. May approve or return; cannot edit the programme.</p></div>
                        <b>{selected.approved_at ? "Approved" : approvalStage === "EXECUTIVE_APPROVAL" ? "Current" : "Pending"}</b>
                      </article>
                    </section>

                    <div className="qms-audit-programme-flow__role-boundary">
                      <LockKeyhole size={16} />
                      <span><strong>Separation of duties is enforced.</strong> The submitter cannot perform Quality review, the Quality Manager cannot final-approve, and the Accountable Executive cannot alter programme content.</span>
                    </div>

                    <section
                      className={`qms-audit-programme-flow__readiness ${readiness.ready_for_approval ? "is-ready" : "is-blocked"}`}
                      aria-label="Programme approval status"
                    >
                      <div>
                        {readiness.ready_for_approval ? (
                          <CheckCircle2 size={18} />
                        ) : (
                          <TriangleAlert size={18} />
                        )}
                        <span>
                          <strong>
                            {readiness.ready_for_approval
                              ? approvalStage === "QUALITY_REVIEW"
                                ? "Ready for Quality Manager review"
                                : approvalStage === "EXECUTIVE_APPROVAL"
                                  ? "Ready for Accountable Executive approval"
                                  : approvalStage === "READY_TO_PUBLISH"
                                    ? "Approved and ready to publish"
                                    : approvalStage === "PUBLISHED"
                                      ? "Approved programme is live"
                                      : "Ready to submit for approval"
                              : "Not ready for approval yet"}
                          </strong>
                          <small>
                            {readiness.ready_for_approval
                              ? selected.status === "ACTIVE"
                                ? "Assigned schedules are available to personal calendar subscriptions."
                                : "All required setup is complete for this frozen revision."
                              : "Complete the items below before submitting."}
                          </small>
                        </span>
                      </div>
                      {!readiness.ready_for_approval &&
                      readiness.blockers.length ? (
                        <ul>
                          {readiness.blockers
                            .slice(0, 8)
                            .map((blocker, index) => (
                              <li key={`${blocker.code}-${index}`}>
                                {blocker.message}
                              </li>
                            ))}
                        </ul>
                      ) : null}
                    </section>

                    <section
                      className="qms-audit-programme-flow__readiness-stats qms-audit-programme-flow__readiness-stats--four"
                      aria-label="Programme summary"
                    >
                      <article>
                        <span>Audits in programme</span>
                        <strong>{readiness.requirement_count}</strong>
                        <small>
                          {readiness.mandatory_requirement_count
                            ? `${readiness.mandatory_requirement_count} mandatory`
                            : "No mandatory audits flagged"}
                        </small>
                      </article>
                      <article>
                        <span>Need scheduling</span>
                        <strong>
                          {readiness.unscheduled_requirement_count}
                        </strong>
                        <small>
                          {unscheduledItems.length
                            ? "Assign calendar dates after approval"
                            : "All audits have schedule links or are complete"}
                        </small>
                      </article>
                      <article>
                        <span>Created on publish</span>
                        <strong>{autoPublishItems.length}</strong>
                        <small>Fixed-date schedules generated automatically</small>
                      </article>
                      <article>
                        <span>Notification policy</span>
                        <strong>{auditorNoticeCount + auditeeNoticeCount}</strong>
                        <small>{auditorNoticeCount} auditor · {auditeeNoticeCount} auditee distributions enabled</small>
                      </article>
                    </section>

                    <section
                      className="qms-audit-programme-flow__approval-panel"
                      aria-label="Approval actions"
                    >
                      <div className="qms-audit-programme-flow__approval-copy">
                        <strong>
                          {approvalStage === "PREPARATION"
                            ? "Quality Officer action"
                            : approvalStage === "QUALITY_REVIEW"
                              ? "Quality Manager action"
                              : approvalStage === "EXECUTIVE_APPROVAL"
                                ? "Accountable Executive action"
                                : approvalStage === "READY_TO_PUBLISH"
                                  ? "Controlled distribution"
                                  : approvalStage === "PUBLISHED"
                                    ? "Programme published"
                                    : "Controlled revision"}
                        </strong>
                        <p>
                          {approvalStage === "PREPARATION"
                            ? "Resolve every blocker, state the submission reason, then submit the completed revision for independent Quality review."
                            : approvalStage === "QUALITY_REVIEW"
                              ? "The submitted revision is frozen. The Quality Manager must independently return it or forward it to the Accountable Executive."
                              : approvalStage === "EXECUTIVE_APPROVAL"
                                ? "Quality review is complete. The Accountable Executive may return the frozen revision or give final approval."
                                : approvalStage === "READY_TO_PUBLISH"
                                  ? "Download the controlled schedule, then publish it to create configured fixed-date schedules and notify assigned teams and auditees."
                                  : approvalStage === "PUBLISHED"
                                    ? "Assigned internal users now receive changes through the unified personal calendar feed; external auditees receive governed notices."
                                    : "This revision is retained as controlled history. Create an amendment for further changes."}
                        </p>
                      </div>

                      {actionFeedback ? <div className="qms-audit-programme-flow__action-feedback" role="status"><CheckCircle2 size={15} /> {actionFeedback}</div> : null}

                      {approvalStage !== "PUBLISHED" || canManage ? (
                        <div className="qms-audit-programme-flow__approval-actions">
                          <input
                            aria-label="Reason for this action"
                            value={actionReason}
                            onChange={(event) => {
                              setActionReason(event.target.value);
                              setActionFeedback(null);
                            }}
                            placeholder={approvalStage === "PREPARATION" ? "Submission rationale (required)" : "Decision or publication rationale (required)"}
                          />

                          {approvalStage === "PREPARATION" && canManage ? (
                            <>
                              <button
                                type="button"
                                className="is-primary"
                                disabled={!readiness.ready_for_approval || actionReason.trim().length < 3 || transitionMutation.isPending}
                                onClick={() =>
                                  transitionMutation.mutate({
                                    target: "UNDER_REVIEW",
                                    reason: actionReason,
                                  })
                                }
                              >
                                <Send size={14} /> Submit for Quality review <ArrowRight size={14} />
                              </button>
                              <button
                                type="button"
                                className="is-danger"
                                disabled={transitionMutation.isPending}
                                onClick={() => {
                                  setDiscardReason(actionReason.trim() || "");
                                  setShowDiscardConfirm(true);
                                }}
                                title="Close and discard this draft programme for the year"
                              >
                                <Trash2 size={14} /> Discard draft
                              </button>
                            </>
                          ) : null}

                          {approvalStage === "QUALITY_REVIEW" && canQualityReview ? (
                            <>
                              <button
                                type="button"
                                className="is-secondary"
                                disabled={actionReason.trim().length < 3 || qualityReviewMutation.isPending}
                                onClick={() => qualityReviewMutation.mutate("RETURN")}
                              >
                                Return to draft
                              </button>
                              <button
                                type="button"
                                className="is-primary"
                                disabled={
                                  !readiness.ready_for_approval ||
                                  actionReason.trim().length < 3 ||
                                  qualityReviewMutation.isPending ||
                                  selected.submitted_by_user_id === currentUser?.id
                                }
                                title={selected.submitted_by_user_id === currentUser?.id ? "A different Quality Manager must review a revision you submitted." : undefined}
                                onClick={() => qualityReviewMutation.mutate("FORWARD")}
                              >
                                <UserCheck size={14} /> Complete Quality review <ArrowRight size={14} />
                              </button>
                            </>
                          ) : null}

                          {approvalStage === "EXECUTIVE_APPROVAL" && canApprove ? (
                            <>
                              <button
                                type="button"
                                className="is-secondary"
                                disabled={actionReason.trim().length < 3 || transitionMutation.isPending}
                                onClick={() =>
                                  transitionMutation.mutate({
                                    target: "DRAFT",
                                    reason: actionReason,
                                  })
                                }
                              >
                                Return for changes
                              </button>
                              <button
                                type="button"
                                className="is-primary"
                                disabled={!readiness.ready_for_approval || actionReason.trim().length < 3 || transitionMutation.isPending}
                                onClick={() =>
                                  transitionMutation.mutate({
                                    target: "APPROVED",
                                    reason: actionReason,
                                  })
                                }
                              >
                                <FileCheck2 size={14} /> Give final approval <ArrowRight size={14} />
                              </button>
                            </>
                          ) : null}

                          {approvalStage === "READY_TO_PUBLISH" && canManage ? (
                            <button
                              type="button"
                              className="is-primary"
                              disabled={actionReason.trim().length < 3 || transitionMutation.isPending}
                              onClick={() =>
                                transitionMutation.mutate({
                                  target: "ACTIVE",
                                  reason: actionReason,
                                })
                              }
                            >
                              <CalendarCheck2 size={14} /> Publish, schedule & notify <ArrowRight size={14} />
                            </button>
                          ) : null}

                          {programmeIsControlled(selected) && canManage ? (
                            <button
                              type="button"
                              className="is-secondary"
                              disabled={actionReason.trim().length < 3 || amendmentMutation.isPending}
                              onClick={() => amendmentMutation.mutate()}
                            >
                              Create amendment
                            </button>
                          ) : null}
                        </div>
                      ) : null}

                      {approvalStage === "PREPARATION" && !canManage ? <small className="qms-audit-programme-flow__waiting">Waiting for a Quality Officer or Quality Manager to complete and submit the draft.</small> : null}
                      {approvalStage === "QUALITY_REVIEW" && !canQualityReview ? <small className="qms-audit-programme-flow__waiting">Waiting for an independent Quality Manager. Quality Officers and AMO administrators cannot perform this decision.</small> : null}
                      {approvalStage === "EXECUTIVE_APPROVAL" && !canApprove ? <small className="qms-audit-programme-flow__waiting">Waiting for the Accountable Executive. Quality personnel cannot give final approval.</small> : null}
                      {approvalStage === "READY_TO_PUBLISH" && !canManage ? <small className="qms-audit-programme-flow__waiting">Final approval is complete. A Quality Officer or Quality Manager must publish the controlled schedule.</small> : null}
                    </section>

                    <details className="qms-audit-programme-flow__history">
                      <summary>
                        Programme history{" "}
                        <small>{selected.events?.length || 0} events</small>
                      </summary>
                      <div>
                        {[...(selected.events || [])].reverse().map((event) => (
                          <article key={event.id}>
                            <span>
                              <strong>{human(event.event_type)}</strong>
                              <small>
                                {new Date(event.created_at).toLocaleString()}
                              </small>
                            </span>
                            <p>{event.reason}</p>
                          </article>
                        ))}
                      </div>
                    </details>
                  </>
                ) : null}
              </>
            )}
          </section>
        </div>
      )}

      <Drawer
        title={
          calendarMonthTarget
            ? `${calendarMonthTarget.mode === "create" ? "Plan another" : "Plan"} ${calendarMonthTarget.item.auditable_entity?.display_label || calendarMonthTarget.item.title} audit · ${new Date(2000, calendarMonthTarget.month - 1, 1).toLocaleString(undefined, { month: "long" })}`
            : "Plan audit month"
        }
        isOpen={Boolean(calendarMonthTarget)}
        onClose={() => setCalendarMonthTarget(null)}
        side="right"
        panelClassName="qms-audit-programme-drawer qms-programme-month-drawer"
      >
        {calendarMonthTarget ? (
          <form
            className="qms-audit-programme__form"
            noValidate={calendarMonthForm.dates.length === 0}
            onSubmit={(event) => {
              event.preventDefault();
              calendarMonthMutation.mutate();
            }}
          >
            <div className="qms-audit-programme-drawer__body">
              <div className="qms-programme-month-drawer__summary is-wide">
                <span>
                  <strong>{calendarMonthTarget.item.title}</strong>
                  <small>
                    {human(calendarMonthTarget.item.audit_type)} ·{" "}
                    {human(calendarMonthTarget.item.state)}
                  </small>
                </span>
                <b
                  className={`qms-chip qms-chip--${statusTone(calendarMonthTarget.item.state)}`}
                >
                  {human(calendarMonthTarget.item.state)}
                </b>
              </div>
              {calendarMonthTarget.mode === "create" ? (
                <p className="qms-audit-programme-flow__drawer-note is-wide">
                  This creates an additional audit requirement. The existing{" "}
                  <strong>{dateLabel(calendarMonthTarget.item.target_start)}</strong>{" "}
                  audit remains unchanged, including its scope, dates, and
                  audit trail.
                </p>
              ) : calendarMonthTarget.item.recurrence !== "FIXED_DATES" ? (
                <p className="qms-audit-programme-flow__drawer-note is-wide">
                  Saving exact dates converts this requirement from{" "}
                  <strong>{human(calendarMonthTarget.item.recurrence)}</strong>{" "}
                  to a governed date series while preserving its duration and
                  controlled history.
                </p>
              ) : (
                <div className="qms-audit-programme-flow__drawer-note is-wide">
                  <span>
                    Dates saved here join this audit series and share its scope,
                    team, and notification policy.
                  </span>{" "}
                  <button
                    type="button"
                    className="qms-audit-programme-flow__inline-action"
                    onClick={openSeparateAuditFromCalendarMonth}
                  >
                    Create a separate audit instead
                  </button>
                </div>
              )}
              <fieldset className="is-wide qms-programme-date-pattern qms-programme-date-pattern--month">
                <legend>
                  Audit date{calendarMonthForm.dates.length === 1 ? "" : "s"}
                </legend>
                {calendarMonthForm.dates.map((value, index) => (
                  <div
                    className="qms-programme-date-pattern__row"
                    key={`calendar-month-date-${index}`}
                  >
                    <input
                      required
                      type="date"
                      min={programmeDate(
                        selected?.programme_year || year,
                        calendarMonthTarget.month,
                        1,
                      )}
                      max={programmeDate(
                        selected?.programme_year || year,
                        calendarMonthTarget.month,
                        new Date(
                          selected?.programme_year || year,
                          calendarMonthTarget.month,
                          0,
                        ).getDate(),
                      )}
                      value={value}
                      onChange={(event) =>
                        setCalendarMonthForm((current) => ({
                          ...current,
                          dates: current.dates.map((entry, entryIndex) =>
                            entryIndex === index ? event.target.value : entry,
                          ),
                        }))
                      }
                    />
                    <small>{weekendAdjustment(value) || "Working day"}</small>
                    <button
                      type="button"
                      className="is-icon is-danger"
                      title="Remove this date"
                      aria-label={`Remove audit date ${index + 1}`}
                      onClick={() =>
                        setCalendarMonthForm((current) => ({
                          ...current,
                          dates: current.dates.filter(
                            (_, entryIndex) => entryIndex !== index,
                          ),
                        }))
                      }
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="is-secondary qms-programme-date-pattern__add"
                  onClick={() =>
                    setCalendarMonthForm((current) => ({
                      ...current,
                      dates: [
                        ...current.dates,
                        programmeDate(
                          selected?.programme_year || year,
                          calendarMonthTarget.month,
                          Math.min(28, 15 + current.dates.length),
                        ),
                      ],
                    }))
                  }
                >
                  <Plus size={14} /> Add another date
                </button>
                <p>
                  Weekend dates move to the next working day when the approved
                  programme is published.
                </p>
              </fieldset>
              <label>
                <span>Start time</span>
                <input
                  type="time"
                  min="09:00"
                  max="17:00"
                  required={calendarMonthForm.dates.length > 0}
                  value={calendarMonthForm.default_start_time}
                  onChange={(event) =>
                    setCalendarMonthForm((current) => ({
                      ...current,
                      default_start_time: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                <span>End time</span>
                <input
                  type="time"
                  min="09:00"
                  max="17:00"
                  required={calendarMonthForm.dates.length > 0}
                  value={calendarMonthForm.default_end_time}
                  onChange={(event) =>
                    setCalendarMonthForm((current) => ({
                      ...current,
                      default_end_time: event.target.value,
                    }))
                  }
                />
              </label>
              <ProgrammeLocationSelect
                id="programme-month-location"
                value={calendarMonthForm.default_location}
                locations={locations}
                onChange={(default_location) =>
                  setCalendarMonthForm((current) => ({
                    ...current,
                    default_location,
                  }))
                }
                required={
                  calendarMonthForm.dates.length > 0 &&
                  ["FACILITY", "STATION"].includes(
                    calendarMonthTarget.item.auditable_entity?.entity_type || "",
                  )
                }
              />
              <label>
                <span>Lead auditor</span>
                <select
                  value={calendarMonthForm.lead_auditor_user_id}
                  onChange={(event) =>
                    setCalendarMonthForm((current) => ({
                      ...current,
                      lead_auditor_user_id: event.target.value,
                      observer_auditor_user_id:
                        current.observer_auditor_user_id === event.target.value
                          ? ""
                          : current.observer_auditor_user_id,
                      supporting_auditor_user_ids: withoutLeadAuditor(
                        current.supporting_auditor_user_ids,
                        event.target.value,
                        current.observer_auditor_user_id,
                      ),
                    }))
                  }
                >
                  <option value="">Assign later</option>
                  {leadAuditorOptions.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.full_name}
                    </option>
                  ))}
                </select>
                {leadOptionsAreFallbackAuditors ? (
                  <small>
                    No lead-auditor privilege holders — auditors may lead this
                    planned audit.
                  </small>
                ) : null}
              </label>
              <ProgrammeObserverSelect
                id="programme-month-observer"
                people={auditorOptions}
                leadAuditorUserId={calendarMonthForm.lead_auditor_user_id}
                supportingAuditorUserIds={
                  calendarMonthForm.supporting_auditor_user_ids
                }
                value={calendarMonthForm.observer_auditor_user_id}
                onChange={(observer_auditor_user_id) =>
                  setCalendarMonthForm((current) => ({
                    ...current,
                    observer_auditor_user_id,
                    supporting_auditor_user_ids: withoutLeadAuditor(
                      current.supporting_auditor_user_ids,
                      current.lead_auditor_user_id,
                      observer_auditor_user_id,
                    ),
                  }))
                }
              />
              <label>
                <span>Auditee representative</span>
                <select
                  value={calendarMonthForm.auditee_user_id}
                  onChange={(event) =>
                    setCalendarMonthForm((current) => ({
                      ...current,
                      auditee_user_id: event.target.value,
                    }))
                  }
                >
                  <option value="">Use the audit area owner</option>
                  {people.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.full_name}
                    </option>
                  ))}
                </select>
              </label>
              <SupportingAuditorPicker
                id="programme-month-supporting-auditors"
                people={auditorOptions}
                leadAuditorUserId={calendarMonthForm.lead_auditor_user_id}
                excludedUserIds={[calendarMonthForm.observer_auditor_user_id]}
                value={calendarMonthForm.supporting_auditor_user_ids}
                onChange={(supporting_auditor_user_ids) =>
                  setCalendarMonthForm((current) => ({
                    ...current,
                    supporting_auditor_user_ids,
                  }))
                }
              />
              <div className="is-wide qms-programme-month-drawer__notifications">
                <label className="is-checkbox">
                  <input
                    type="checkbox"
                    checked={calendarMonthForm.notify_auditors}
                    onChange={(event) =>
                      setCalendarMonthForm((current) => ({
                        ...current,
                        notify_auditors: event.target.checked,
                      }))
                    }
                  />
                  <span>Notify audit team on publication</span>
                </label>
                <label className="is-checkbox">
                  <input
                    type="checkbox"
                    checked={calendarMonthForm.notify_auditees}
                    onChange={(event) =>
                      setCalendarMonthForm((current) => ({
                        ...current,
                        notify_auditees: event.target.checked,
                      }))
                    }
                  />
                  <span>Notify auditee representative on publication</span>
                </label>
              </div>
            </div>
            <div className="qms-audit-programme-drawer__footer">
              <button
                type="button"
                className="is-secondary"
                onClick={() => setCalendarMonthTarget(null)}
              >
                Cancel
              </button>
              {calendarMonthTarget.mode === "update" &&
              canManage &&
              editableProgrammeIds.has(
                calendarMonthTarget.item.programme_id,
              ) ? (
                <button
                  type="button"
                  className="is-danger"
                  disabled={calendarMonthMutation.isPending}
                  onClick={() => openRemoveAudit(calendarMonthTarget.item)}
                >
                  <Trash2 size={14} /> Delete audit
                </button>
              ) : null}
              <button
                type={calendarMonthForm.dates.length ? "submit" : "button"}
                className={
                  calendarMonthForm.dates.length ? "is-primary" : "is-danger"
                }
                disabled={
                  calendarMonthMutation.isPending ||
                  (calendarMonthTarget.mode === "create"
                    ? !calendarMonthForm.dates.length
                    : false) ||
                  (calendarMonthForm.dates.length > 0 &&
                    !calendarMonthForm.dates.every(Boolean)) ||
                  (calendarMonthForm.dates.length > 0 &&
                    calendarMonthForm.default_start_time >=
                      calendarMonthForm.default_end_time)
                }
                onClick={
                  calendarMonthForm.dates.length
                    ? undefined
                    : () => calendarMonthMutation.mutate()
                }
              >
                {calendarMonthForm.dates.length ? (
                  <CalendarClock size={14} />
                ) : (
                  <Trash2 size={14} />
                )}{" "}
                {calendarMonthTarget.mode === "create"
                  ? "Create additional audit"
                  : calendarMonthForm.dates.length
                    ? `Save ${new Date(2000, calendarMonthTarget.month - 1, 1).toLocaleString(undefined, { month: "long" })} dates`
                    : `Remove ${new Date(2000, calendarMonthTarget.month - 1, 1).toLocaleString(undefined, { month: "long" })} dates`}
              </button>
            </div>
          </form>
        ) : null}
      </Drawer>

      <Drawer
        title="Create programme"
        isOpen={showCreate}
        onClose={() => setShowCreate(false)}
        side="right"
        panelClassName="qms-audit-programme-drawer qms-audit-programme-flow__create-drawer"
      >
        <form
          className="qms-audit-programme__form qms-audit-programme-flow__create"
          onSubmit={(event) => {
            event.preventDefault();
            createProgrammeMutation.mutate();
          }}
        >
          <div className="qms-audit-programme-drawer__body">
            <label className="is-wide">
              <span>Type</span>
              <select
                required
                value={programmeForm.programme_kind}
                onChange={(event) => {
                  const programme_kind = event.target.value as ProgrammeKind;
                  const copy_previous_year = defaultCopyPreviousYear(
                    priorYearProgrammes,
                    programme_kind,
                  );
                  setProgrammeForm((current) => ({
                    ...current,
                    programme_kind,
                    title: programmeKindTitle(programme_kind, year),
                    copy_previous_year,
                    rotate_auditors: defaultRotateAuditors(copy_previous_year),
                  }));
                }}
              >
                {PROGRAMME_KINDS.filter((entry) =>
                  creatableKinds.includes(entry.id),
                ).map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.label}
                  </option>
                ))}
              </select>
            </label>
            <p className="qms-audit-programme-flow__drawer-note is-compact">
              <strong>{programmeForm.title}</strong> ·{" "}
              {dateLabel(programmeForm.period_start)} →{" "}
              {dateLabel(programmeForm.period_end)}
            </p>
            <label className="is-wide is-checkbox">
              <input
                type="checkbox"
                checked={programmeForm.copy_previous_year}
                onChange={(event) => {
                  const copy_previous_year = event.target.checked;
                  setProgrammeForm((current) => ({
                    ...current,
                    copy_previous_year,
                    rotate_auditors: defaultRotateAuditors(copy_previous_year),
                  }));
                }}
              />
              <span>Carry forward from {priorYear}</span>
            </label>
            <label className="is-wide is-checkbox">
              <input
                type="checkbox"
                checked={
                  programmeForm.copy_previous_year &&
                  programmeForm.rotate_auditors
                }
                disabled={!programmeForm.copy_previous_year}
                onChange={(event) =>
                  setProgrammeForm((current) => ({
                    ...current,
                    rotate_auditors: event.target.checked,
                  }))
                }
              />
              <span>Rotate auditors</span>
            </label>
            {programmeForm.copy_previous_year &&
            !priorYearCarryForwardAvailable(
              priorYearProgrammes,
              programmeForm.programme_kind,
            ) ? (
              <p className="qms-audit-programme-flow__drawer-note is-compact">
                No {priorYear} programme of this type yet.
              </p>
            ) : null}
            <label className="is-wide is-checkbox">
              <input
                type="checkbox"
                checked={programmeForm.apply_hybrid_seed}
                onChange={(event) =>
                  setProgrammeForm((current) => ({
                    ...current,
                    apply_hybrid_seed: event.target.checked,
                  }))
                }
              />
              <span>Hybrid seed</span>
            </label>
            <HistoryTextarea
              label="Objectives"
              rows={3}
              value={programmeForm.objectives}
              options={objectivesHistory.options}
              listId={`${objectivesHistory.listId}-create`}
              onRemember={objectivesHistory.remember}
              onChange={(objectives) =>
                setProgrammeForm((current) => ({
                  ...current,
                  objectives,
                }))
              }
            />
            <HistoryTextarea
              label="Compliance baseline"
              rows={3}
              placeholder="KCAR / MPM / QMSM / contractual requirement"
              value={programmeForm.regulatory_basis}
              options={basisHistory.options}
              listId={`${basisHistory.listId}-create`}
              onRemember={basisHistory.remember}
              onChange={(regulatory_basis) =>
                setProgrammeForm((current) => ({
                  ...current,
                  regulatory_basis,
                }))
              }
            />
          </div>
          <div className="qms-audit-programme-drawer__footer">
            <button
              type="button"
              className="is-secondary"
              onClick={() => setShowCreate(false)}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="is-primary"
              disabled={createProgrammeMutation.isPending}
            >
              Create draft programme
            </button>
          </div>
        </form>
      </Drawer>

      <Drawer
        title="Add audit to programme"
        isOpen={showRequirement}
        onClose={() => setShowRequirement(false)}
        side="right"
        panelClassName="qms-audit-programme-drawer"
      >
        <form
          className="qms-audit-programme__form"
          onSubmit={(event) => {
            event.preventDefault();
            itemMutation.mutate();
          }}
        >
          <div className="qms-audit-programme-drawer__body">
            <p className="qms-audit-programme-flow__drawer-note">
              Pick the area to audit and how often it should be reviewed.
            </p>
            <label>
              <span>Audit area</span>
              <select
                required
                value={itemForm.universe_item_id}
                onChange={(event) => {
                  const universeId = event.target.value;
                  const entity = programmeUniverseItems.find(
                    (item) => item.id === universeId,
                  );
                  setItemForm((current) => ({
                    ...current,
                    universe_item_id: universeId,
                    audit_type: auditTypeForEntity(entity?.entity_type),
                    title:
                      current.title ||
                      (entity ? `${entity.display_label} audit` : ""),
                    scope: current.scope || entity?.display_label || "",
                    default_location:
                      current.default_location ||
                      suggestedLocationCode(entity, locations),
                    mandatory_surveillance:
                      current.mandatory_surveillance ||
                      Boolean(entity?.mandatory_surveillance),
                  }));
                }}
              >
                <option value="">Select entity</option>
                {programmeUniverseItems
                  .filter((item) => item.active)
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.display_label} · {human(item.entity_type)}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              <span>Audit type</span>
              <input
                readOnly
                value={auditTypeLabel(itemForm.audit_type)}
                aria-readonly="true"
              />
            </label>
            <label>
              <span>Frequency</span>
              <select
                value={itemForm.recurrence}
                onChange={(event) =>
                  setItemForm((current) => ({
                    ...current,
                    recurrence: event.target.value as AuditProgrammeRecurrence,
                  }))
                }
              >
                {RECURRENCES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="is-wide">
              <span>Audit title</span>
              <input
                required
                minLength={3}
                value={itemForm.title}
                onChange={(event) =>
                  setItemForm((current) => ({
                    ...current,
                    title: event.target.value,
                  }))
                }
              />
            </label>
            <HistoryTextarea
              label="Purpose"
              rows={2}
              value={itemForm.purpose}
              options={purposeHistoryAdd.options}
              listId={`${purposeHistoryAdd.listId}-add`}
              onRemember={purposeHistoryAdd.remember}
              onChange={(purpose) =>
                setItemForm((current) => ({ ...current, purpose }))
              }
            />
            <HistoryTextarea
              label="Scope"
              rows={3}
              required
              value={itemForm.scope}
              options={scopeHistoryAdd.options}
              listId={`${scopeHistoryAdd.listId}-add`}
              onRemember={scopeHistoryAdd.remember}
              onChange={(scope) =>
                setItemForm((current) => ({ ...current, scope }))
              }
            />
            <HistoryTextarea
              label="Criteria"
              rows={3}
              required
              value={itemForm.criteria}
              options={criteriaHistoryAdd.options}
              listId={`${criteriaHistoryAdd.listId}-add`}
              onRemember={criteriaHistoryAdd.remember}
              onChange={(criteria) =>
                setItemForm((current) => ({ ...current, criteria }))
              }
            />
            {itemForm.recurrence === "FIXED_DATES" ? (
              <fieldset className="is-wide qms-programme-date-pattern">
                <legend>Dates each calendar year</legend>
                <p>
                  Weekend dates automatically move to the next Monday. The
                  affected users are notified.
                </p>
                {itemForm.fixed_dates.map((value, index) => (
                  <div
                    className="qms-programme-date-pattern__row"
                    key={`fixed-date-${index}`}
                  >
                    <input
                      required
                      type="date"
                      min={`${year}-01-01`}
                      max={`${year}-12-31`}
                      value={value}
                      onChange={(event) =>
                        setItemForm((current) => ({
                          ...current,
                          fixed_dates: current.fixed_dates.map(
                            (entry, entryIndex) =>
                              entryIndex === index ? event.target.value : entry,
                          ),
                        }))
                      }
                    />
                    <small>{weekendAdjustment(value) || "Working day"}</small>
                    {itemForm.fixed_dates.length > 1 ? (
                      <button
                        type="button"
                        className="is-icon is-danger"
                        aria-label={`Remove date ${index + 1}`}
                        onClick={() =>
                          setItemForm((current) => ({
                            ...current,
                            fixed_dates: current.fixed_dates.filter(
                              (_, entryIndex) => entryIndex !== index,
                            ),
                          }))
                        }
                      >
                        <Trash2 size={14} />
                      </button>
                    ) : null}
                  </div>
                ))}
                <button
                  type="button"
                  className="is-secondary qms-programme-date-pattern__add"
                  onClick={() =>
                    setItemForm((current) => ({
                      ...current,
                      fixed_dates: [...current.fixed_dates, ""],
                    }))
                  }
                >
                  <Plus size={14} /> Add another date
                </button>
              </fieldset>
            ) : (
              <>
                <label>
                  <span>Target window start</span>
                  <input
                    required
                    type="date"
                    value={itemForm.target_start}
                    onChange={(event) =>
                      setItemForm((current) => ({
                        ...current,
                        target_start: event.target.value,
                      }))
                    }
                  />
                </label>
                <label>
                  <span>Target window end</span>
                  <input
                    required
                    type="date"
                    value={itemForm.target_end}
                    onChange={(event) =>
                      setItemForm((current) => ({
                        ...current,
                        target_end: event.target.value,
                      }))
                    }
                  />
                </label>
              </>
            )}
            <label>
              <span>Start time</span>
              <input
                type="time"
                min="09:00"
                max="17:00"
                required
                value={itemForm.default_start_time}
                onChange={(event) =>
                  setItemForm((current) => ({
                    ...current,
                    default_start_time: event.target.value,
                  }))
                }
              />
            </label>
            <label>
              <span>End time</span>
              <input
                type="time"
                min="09:00"
                max="17:00"
                required
                value={itemForm.default_end_time}
                onChange={(event) =>
                  setItemForm((current) => ({
                    ...current,
                    default_end_time: event.target.value,
                  }))
                }
              />
            </label>
            <ProgrammeLocationSelect
              id="programme-item-location"
              value={itemForm.default_location}
              locations={locations}
              onChange={(default_location) =>
                setItemForm((current) => ({ ...current, default_location }))
              }
              required={["FACILITY", "STATION"].includes(
                programmeUniverseItems.find(
                  (entry) => entry.id === itemForm.universe_item_id,
                )?.entity_type || "",
              )}
            />
            <label>
              <span>Lead auditor</span>
              <select
                value={itemForm.lead_auditor_user_id}
                onChange={(event) =>
                  setItemForm((current) => ({
                    ...current,
                    lead_auditor_user_id: event.target.value,
                    observer_auditor_user_id:
                      current.observer_auditor_user_id === event.target.value
                        ? ""
                        : current.observer_auditor_user_id,
                    supporting_auditor_user_ids: withoutLeadAuditor(
                      current.supporting_auditor_user_ids,
                      event.target.value,
                      current.observer_auditor_user_id,
                    ),
                  }))
                }
              >
                <option value="">Assign later</option>
                {leadAuditorOptions.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name}
                  </option>
                ))}
              </select>
              {leadOptionsAreFallbackAuditors ? (
                <small>
                  No lead-auditor privilege holders — auditors may lead this
                  planned audit.
                </small>
              ) : null}
            </label>
            <ProgrammeObserverSelect
              id="programme-item-observer"
              people={auditorOptions}
              leadAuditorUserId={itemForm.lead_auditor_user_id}
              supportingAuditorUserIds={itemForm.supporting_auditor_user_ids}
              value={itemForm.observer_auditor_user_id}
              onChange={(observer_auditor_user_id) =>
                setItemForm((current) => ({
                  ...current,
                  observer_auditor_user_id,
                  supporting_auditor_user_ids: withoutLeadAuditor(
                    current.supporting_auditor_user_ids,
                    current.lead_auditor_user_id,
                    observer_auditor_user_id,
                  ),
                }))
              }
            />
            <label>
              <span>Auditee representative</span>
              <select
                value={itemForm.auditee_user_id}
                onChange={(event) =>
                  setItemForm((current) => ({
                    ...current,
                    auditee_user_id: event.target.value,
                  }))
                }
              >
                <option value="">Use selected area</option>
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name}
                  </option>
                ))}
              </select>
            </label>
            <SupportingAuditorPicker
              id="programme-item-supporting-auditors"
              people={auditorOptions}
              leadAuditorUserId={itemForm.lead_auditor_user_id}
              excludedUserIds={[itemForm.observer_auditor_user_id]}
              value={itemForm.supporting_auditor_user_ids}
              onChange={(supporting_auditor_user_ids) =>
                setItemForm((current) => ({
                  ...current,
                  supporting_auditor_user_ids,
                }))
              }
            />
            <label className="is-checkbox">
              <input
                type="checkbox"
                checked={itemForm.mandatory_surveillance}
                onChange={(event) =>
                  setItemForm((current) => ({
                    ...current,
                    mandatory_surveillance: event.target.checked,
                  }))
                }
              />
              <span>Mandatory / minimum surveillance</span>
            </label>
          </div>
          <div className="qms-audit-programme-drawer__footer">
            <button
              type="button"
              className="is-secondary"
              onClick={() => setShowRequirement(false)}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="is-primary"
              disabled={
                itemMutation.isPending ||
                (itemForm.recurrence === "FIXED_DATES" &&
                  !itemForm.fixed_dates.some(Boolean))
              }
            >
              Add to programme
            </button>
          </div>
        </form>
      </Drawer>

      <Drawer
        title="Add tenant audit area"
        isOpen={showUniverseCreate}
        onClose={() => setShowUniverseCreate(false)}
        side="right"
        panelClassName="qms-audit-programme-drawer"
      >
        <form
          className="qms-audit-programme__form"
          onSubmit={(event) => {
            event.preventDefault();
            universeMutation.mutate();
          }}
        >
          <div className="qms-audit-programme-drawer__body">
            <p className="qms-audit-programme-flow__drawer-note">
              This row is available only to this tenant and can be scheduled
              into current or future programmes.
            </p>
            <label>
              <span>Use in</span>
              <select
                value={universeForm.programme_kind}
                onChange={(event) =>
                  setUniverseForm((current) => ({
                    ...current,
                    programme_kind: event.target
                      .value as AuditUniverseProgrammeKind,
                  }))
                }
              >
                <option value="INTERNAL">Internal audit programmes</option>
                <option value="EXTERNAL">External audit programmes</option>
                <option value="BOTH">Internal and external programmes</option>
              </select>
            </label>
            <label>
              <span>Area type</span>
              <select
                value={universeForm.entity_type}
                onChange={(event) => {
                  const entityType = event.target
                    .value as AuditUniverseEntityType;
                  setUniverseForm((current) => ({
                    ...current,
                    entity_type: entityType,
                    aircraft_serial_number:
                      entityType === "AIRCRAFT"
                        ? current.aircraft_serial_number
                        : "",
                  }));
                }}
              >
                {UNIVERSE_TYPES.map((value) => (
                  <option key={value} value={value}>
                    {value === "AIRCRAFT"
                      ? "Aircraft (select from Fleet)"
                      : value === "AIRCRAFT_TYPE"
                        ? "Aircraft type / product class"
                        : human(value)}
                  </option>
                ))}
              </select>
            </label>
            {universeForm.entity_type === "AIRCRAFT" ? (
              <>
                <label className="is-wide">
                  <span>Aircraft</span>
                  <select
                    required
                    value={universeForm.aircraft_serial_number}
                    onChange={(event) =>
                      setUniverseForm((current) => ({
                        ...current,
                        aircraft_serial_number: event.target.value,
                      }))
                    }
                  >
                    <option value="">Select an active Fleet aircraft</option>
                    {(aircraftQuery.data || []).map((aircraft) => (
                      <option
                        key={aircraft.serial_number}
                        value={aircraft.serial_number}
                      >
                        {aircraft.registration} ·{" "}
                        {aircraft.model ||
                          aircraft.aircraft_model_code ||
                          "Model not recorded"}{" "}
                        · MSN {aircraft.serial_number}
                      </option>
                    ))}
                  </select>
                </label>
                {aircraftForArea ? (
                  <div className="qms-audit-area-aircraft is-wide">
                    <Plane size={18} aria-hidden="true" />
                    <span>
                      <small>Tail number</small>
                      <strong>{aircraftForArea.registration}</strong>
                    </span>
                    <span>
                      <small>Model</small>
                      <strong>
                        {aircraftForArea.model ||
                          aircraftForArea.aircraft_model_code ||
                          "Not recorded"}
                      </strong>
                    </span>
                    <span>
                      <small>MSN</small>
                      <strong>{aircraftForArea.serial_number}</strong>
                    </span>
                  </div>
                ) : aircraftQuery.isLoading ? (
                  <p className="qms-audit-programme-flow__drawer-note is-wide">
                    Loading active Fleet aircraft…
                  </p>
                ) : !(aircraftQuery.data || []).length ? (
                  <p className="qms-audit-programme-flow__drawer-note is-wide">
                    No active aircraft are available. Add the aircraft to the
                    Fleet register first.
                  </p>
                ) : null}
              </>
            ) : (
              <label className="is-wide">
                <span>Audit area name</span>
                <input
                  required
                  value={universeForm.display_label}
                  onChange={(event) =>
                    setUniverseForm((current) => ({
                      ...current,
                      display_label: event.target.value,
                    }))
                  }
                  placeholder="e.g. NDT workshop or Mombasa line station"
                />
              </label>
            )}
            <label>
              <span>Risk</span>
              <select
                value={universeForm.risk_classification}
                onChange={(event) =>
                  setUniverseForm((current) => ({
                    ...current,
                    risk_classification: event.target.value as AuditRiskLevel,
                  }))
                }
              >
                {RISKS.map((value) => (
                  <option key={value} value={value}>
                    {human(value)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Regulatory criticality</span>
              <select
                value={universeForm.regulatory_criticality}
                onChange={(event) =>
                  setUniverseForm((current) => ({
                    ...current,
                    regulatory_criticality: event.target
                      .value as AuditRiskLevel,
                  }))
                }
              >
                {RISKS.map((value) => (
                  <option key={value} value={value}>
                    {human(value)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Maximum interval</span>
              <select
                value={universeForm.surveillance_interval_days}
                onChange={(event) =>
                  setUniverseForm((current) => ({
                    ...current,
                    surveillance_interval_days: event.target.value,
                  }))
                }
              >
                <option value="90">Every 3 months</option>
                <option value="183">Every 6 months</option>
                <option value="365">Every year</option>
                <option value="730">Every 2 years</option>
              </select>
            </label>
            <label className="is-checkbox">
              <input
                type="checkbox"
                checked={universeForm.mandatory_surveillance}
                onChange={(event) =>
                  setUniverseForm((current) => ({
                    ...current,
                    mandatory_surveillance: event.target.checked,
                  }))
                }
              />
              <span>Mandatory programme coverage</span>
            </label>
            <label className="is-wide">
              <span>Notes</span>
              <textarea
                rows={2}
                value={universeForm.notes}
                onChange={(event) =>
                  setUniverseForm((current) => ({
                    ...current,
                    notes: event.target.value,
                  }))
                }
              />
            </label>
          </div>
          <div className="qms-audit-programme-drawer__footer">
            <button
              type="button"
              className="is-secondary"
              onClick={() => setShowUniverseCreate(false)}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="is-primary"
              disabled={
                universeMutation.isPending ||
                (universeForm.entity_type === "AIRCRAFT"
                  ? !universeForm.aircraft_serial_number
                  : universeForm.display_label.trim().length < 2)
              }
            >
              Add to catalogue
            </button>
          </div>
        </form>
      </Drawer>

      <Drawer
        title="How this programme works"
        isOpen={showMethodologyInfo}
        onClose={() => setShowMethodologyInfo(false)}
        side="right"
        panelClassName="qms-audit-programme-drawer qms-audit-programme-drawer--info"
      >
        {selected ? (
          <>
            <div className="qms-audit-programme-drawer__body">
              <div className="qms-audit-programme-flow__drawer-summary qms-audit-programme-flow__methodology-drawer">
                <p className="qms-audit-programme-flow__drawer-note">
                  Optional detail for quality managers. Day-to-day work is
                  adding audits and scheduling them in Calendar.
                </p>

                <section
                  className="qms-programme-info-overview"
                  aria-label="Assurance methodology"
                >
                  <div className="qms-programme-info-overview__strategy">
                    <span className="qms-programme-info-overview__label">
                      Methodology
                    </span>
                    <strong>
                      {methodologyLabel(selectedModel)}
                      {selected.continuous_monitoring_enabled
                        ? " · Continuous monitoring"
                        : ""}
                    </strong>
                    <div
                      className="qms-programme-info-overview__weights"
                      aria-label="Score weights"
                    >
                      {METHODOLOGY_PILLARS.filter(
                        (pillar) => pillar.id !== "HYBRID",
                      ).map((pillar) => {
                        const weight =
                          pillar.id === "COMPLIANCE"
                            ? optimizer?.weights?.compliance
                            : pillar.id === "RISK"
                              ? optimizer?.weights?.risk
                              : optimizer?.weights?.performance;
                        return (
                          <div key={pillar.id}>
                            <span>{pillar.label}</span>
                            <strong>
                              {typeof weight === "number"
                                ? `${Math.round(weight * 100)}%`
                                : "—"}
                            </strong>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  <dl className="qms-programme-info-overview__stats">
                    <div>
                      <dt>Audits</dt>
                      <dd>{readiness.requirement_count}</dd>
                    </div>
                    <div>
                      <dt>Mandatory</dt>
                      <dd>{readiness.mandatory_requirement_count}</dd>
                    </div>
                    <div>
                      <dt>High risk</dt>
                      <dd>{readiness.high_risk_requirement_count}</dd>
                    </div>
                    <div>
                      <dt>Needs scheduling</dt>
                      <dd>{readiness.unscheduled_requirement_count}</dd>
                    </div>
                  </dl>
                </section>

                <section
                  className="qms-programme-info-optimizer"
                  aria-label="Hybrid assurance optimizer"
                >
                  <header>
                    <div>
                      <strong>
                        <BrainCircuit size={15} aria-hidden /> Assurance
                        optimizer
                      </strong>
                      <p>
                        Compliance, risk, and performance scoring used to
                        recommend coverage.
                      </p>
                    </div>
                    {canManage ? (
                      <button
                        type="button"
                        className="is-secondary"
                        disabled={optimizerMutation.isPending}
                        onClick={() => optimizerMutation.mutate()}
                      >
                        <RefreshCw size={14} aria-hidden /> Recalculate
                      </button>
                    ) : null}
                  </header>
                  {optimizerQuery.isLoading ? (
                    <p className="qms-audit-programme-flow__empty">
                      Calculating surveillance priorities…
                    </p>
                  ) : optimizer ? (
                    <>
                      <div className="qms-programme-info-optimizer__summary">
                        <div>
                          <span>Compliance</span>
                          <strong>
                            {Math.round(
                              (optimizer.weights?.compliance || 0) * 100,
                            )}
                            %
                          </strong>
                        </div>
                        <div>
                          <span>Risk</span>
                          <strong>
                            {Math.round((optimizer.weights?.risk || 0) * 100)}%
                          </strong>
                        </div>
                        <div>
                          <span>Performance</span>
                          <strong>
                            {Math.round(
                              (optimizer.weights?.performance || 0) * 100,
                            )}
                            %
                          </strong>
                        </div>
                        <div>
                          <span>Coverage gaps</span>
                          <strong>
                            {optimizer.summary?.coverage_gaps || 0}
                          </strong>
                        </div>
                      </div>
                      {optimizer.governance?.message ? (
                        <p className="qms-programme-info-optimizer__note">
                          <ShieldCheck size={14} aria-hidden />{" "}
                          {optimizer.governance.message}
                        </p>
                      ) : null}
                      <ul className="qms-programme-info-optimizer__list">
                        {(optimizer.recommendations || [])
                          .filter(
                            (entry) =>
                              entry.recommended_in_current_programme ||
                              entry.in_programme,
                          )
                          .slice(0, 12)
                          .map((entry) => (
                            <li key={entry.universe_item_id}>
                              <div className="qms-programme-info-optimizer__score">
                                <strong>{entry.priority_score}</strong>
                                <span>{human(entry.priority_band)}</span>
                              </div>
                              <div className="qms-programme-info-optimizer__main">
                                <strong title={entry.auditable_entity}>
                                  {entry.auditable_entity}
                                </strong>
                                <p>
                                  Compliance {entry.components.compliance} ·
                                  Risk {entry.components.risk} · Performance{" "}
                                  {entry.components.performance}
                                  {entry.signals.repeat_findings
                                    ? ` · ${entry.signals.repeat_findings} repeat finding(s)`
                                    : ""}
                                  {entry.signals.open_findings
                                    ? ` · ${entry.signals.open_findings} open finding(s)`
                                    : ""}
                                  {" · "}
                                  every {entry.recommended_interval_days} days
                                </p>
                              </div>
                              <div className="qms-programme-info-optimizer__status">
                                {entry.in_programme ? (
                                  <span className="qms-chip qms-chip--good">
                                    Covered
                                  </span>
                                ) : entry.requires_amendment ? (
                                  <span className="qms-chip qms-chip--warn">
                                    Amend
                                  </span>
                                ) : (
                                  <span className="qms-chip">Recommended</span>
                                )}
                                <span>
                                  Due {dateLabel(entry.next_recommended_due)}
                                </span>
                              </div>
                            </li>
                          ))}
                      </ul>
                    </>
                  ) : (
                    <p className="qms-audit-programme-flow__empty">
                      No optimizer result is available.
                    </p>
                  )}
                </section>
              </div>
            </div>
            <div className="qms-audit-programme-drawer__footer">
              <button
                type="button"
                className="is-secondary"
                onClick={() => setShowMethodologyInfo(false)}
              >
                Close
              </button>
            </div>
          </>
        ) : null}
      </Drawer>

      <Drawer
        title="Discard draft programme"
        isOpen={showDiscardConfirm}
        onClose={() => {
          setShowDiscardConfirm(false);
          setDiscardReason("");
        }}
        side="right"
        panelClassName="qms-audit-programme-drawer"
      >
        <form
          className="qms-audit-programme__form"
          onSubmit={(event) => {
            event.preventDefault();
            if (discardReason.trim().length < 3) return;
            transitionMutation.mutate({
              target: "CLOSED",
              reason: discardReason,
            });
          }}
        >
          <div className="qms-audit-programme-drawer__body">
            <p className="qms-audit-programme-flow__drawer-note">
              This closes the draft for {year}
              {selected ? ` · ${programmeDisplayLabel(selected)}` : ""}. You can
              create a fresh programme for the same year afterwards.
            </p>
            <label className="is-wide">
              <span>Reason for discarding</span>
              <textarea
                required
                minLength={3}
                rows={3}
                value={discardReason}
                onChange={(event) => setDiscardReason(event.target.value)}
                placeholder="Why this draft should be closed"
              />
            </label>
          </div>
          <div className="qms-audit-programme-drawer__footer">
            <button
              type="button"
              className="is-secondary"
              onClick={() => {
                setShowDiscardConfirm(false);
                setDiscardReason("");
              }}
            >
              Keep draft
            </button>
            <button
              type="submit"
              className="is-danger"
              disabled={
                discardReason.trim().length < 3 || transitionMutation.isPending
              }
            >
              <Trash2 size={14} /> Discard draft
            </button>
          </div>
        </form>
      </Drawer>

      <Drawer
        title="Remove audit"
        isOpen={Boolean(cancelItemTarget)}
        onClose={() => {
          setCancelItemTarget(null);
          setCancelItemReason("");
        }}
        side="right"
        panelClassName="qms-audit-programme-drawer"
      >
        {cancelItemTarget ? (
          <form
            className="qms-audit-programme__form qms-audit-programme-flow__create"
            onSubmit={(event) => {
              event.preventDefault();
              cancelItemMutation.mutate(cancelItemTarget);
            }}
          >
            <div className="qms-audit-programme-drawer__body">
              <p className="qms-audit-programme-flow__drawer-note is-compact">
                Remove <strong>{cancelItemTarget.title}</strong> from this draft.
              </p>
              <label className="is-wide">
                <span>Reason</span>
                <input
                  required
                  minLength={3}
                  value={cancelItemReason}
                  onChange={(event) => setCancelItemReason(event.target.value)}
                  placeholder="Why this audit is removed"
                />
              </label>
            </div>
            <div className="qms-audit-programme-drawer__footer">
              <button
                type="button"
                className="is-secondary"
                onClick={() => {
                  setCancelItemTarget(null);
                  setCancelItemReason("");
                }}
              >
                Keep
              </button>
              <button
                type="submit"
                className="is-danger"
                disabled={
                  cancelItemMutation.isPending ||
                  cancelItemReason.trim().length < 3
                }
              >
                <Trash2 size={14} /> Delete audit
              </button>
            </div>
          </form>
        ) : null}
      </Drawer>

      <Drawer
        title="Programme details"
        isOpen={showProgrammeDetail}
        onClose={() => setShowProgrammeDetail(false)}
        side="right"
        panelClassName="qms-audit-programme-drawer"
      >
        {selected ? (
          <>
            <div className="qms-audit-programme-drawer__body">
              <div className="qms-audit-programme-flow__drawer-summary">
                {programmeStatusHint(selected.status) ? (
                  <p className="qms-audit-programme-flow__drawer-note">
                    {programmeStatusHint(selected.status)}
                  </p>
                ) : null}
                <dl>
                  <div>
                    <dt>Programme</dt>
                    <dd>{programmeDisplayLabel(selected)}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{human(selected.status)}</dd>
                  </div>
                  <div>
                    <dt>Period</dt>
                    <dd>
                      {dateLabel(selected.period_start)} →{" "}
                      {dateLabel(selected.period_end)}
                    </dd>
                  </div>
                  <div>
                    <dt>Methodology</dt>
                    <dd>{methodologyLabel(selected.assurance_model)}</dd>
                  </div>
                  <div>
                    <dt>Objectives</dt>
                    <dd>{(selected.objectives || []).join("; ") || "—"}</dd>
                  </div>
                  <div>
                    <dt>Regulatory basis</dt>
                    <dd>{linesOf(selected.regulatory_basis) || "—"}</dd>
                  </div>
                  <div>
                    <dt>Audits in programme</dt>
                    <dd>{readiness.requirement_count}</dd>
                  </div>
                  <div>
                    <dt>Need scheduling</dt>
                    <dd>{readiness.unscheduled_requirement_count}</dd>
                  </div>
                </dl>
              </div>
            </div>
            <div className="qms-audit-programme-drawer__footer">
              <button
                type="button"
                className="is-secondary"
                onClick={() => setShowProgrammeDetail(false)}
              >
                Close
              </button>
              {canManage && selected.status === "DRAFT" ? (
                <button
                  type="button"
                  className="is-danger"
                  onClick={() => {
                    setShowProgrammeDetail(false);
                    setDiscardReason("");
                    setShowDiscardConfirm(true);
                  }}
                >
                  <Trash2 size={14} /> Discard draft
                </button>
              ) : null}
              {canManage && programmeEditable(selected.status) ? (
                <button
                  type="button"
                  className="is-primary"
                  onClick={() => {
                    setShowProgrammeDetail(false);
                    openProgrammeEdit(selected);
                  }}
                >
                  <Pencil size={14} /> Edit programme
                </button>
              ) : null}
            </div>
          </>
        ) : null}
      </Drawer>

      <Drawer
        title="Edit programme"
        isOpen={showProgrammeEdit}
        onClose={() => setShowProgrammeEdit(false)}
        side="right"
        panelClassName="qms-audit-programme-drawer"
      >
        <form
          className="qms-audit-programme__form qms-audit-programme-flow__create"
          onSubmit={(event) => {
            event.preventDefault();
            updateProgrammeMutation.mutate();
          }}
        >
          <div className="qms-audit-programme-drawer__body">
            <p className="qms-audit-programme-flow__drawer-note">
              Editable while draft or under review. A change reason is required.
            </p>
            <label className="is-wide">
              <span>Programme title</span>
              <input
                required
                minLength={3}
                value={editProgrammeForm.title}
                onChange={(event) =>
                  setEditProgrammeForm((current) => ({
                    ...current,
                    title: event.target.value,
                  }))
                }
              />
            </label>
            <label>
              <span>Period start</span>
              <input
                type="date"
                required
                value={editProgrammeForm.period_start}
                onChange={(event) =>
                  setEditProgrammeForm((current) => ({
                    ...current,
                    period_start: event.target.value,
                  }))
                }
              />
            </label>
            <label>
              <span>Period end</span>
              <input
                type="date"
                required
                value={editProgrammeForm.period_end}
                onChange={(event) =>
                  setEditProgrammeForm((current) => ({
                    ...current,
                    period_end: event.target.value,
                  }))
                }
              />
            </label>
            <HistoryTextarea
              label="Objectives"
              rows={3}
              value={editProgrammeForm.objectives}
              options={objectivesHistory.options}
              listId={`${objectivesHistory.listId}-edit`}
              onRemember={objectivesHistory.remember}
              onChange={(objectives) =>
                setEditProgrammeForm((current) => ({
                  ...current,
                  objectives,
                }))
              }
            />
            <HistoryTextarea
              label="Compliance baseline"
              rows={3}
              value={editProgrammeForm.regulatory_basis}
              options={basisHistory.options}
              listId={`${basisHistory.listId}-edit`}
              onRemember={basisHistory.remember}
              onChange={(regulatory_basis) =>
                setEditProgrammeForm((current) => ({
                  ...current,
                  regulatory_basis,
                }))
              }
            />
            <label className="is-wide">
              <span>Change reason</span>
              <input
                required
                minLength={3}
                value={editReason}
                onChange={(event) => setEditReason(event.target.value)}
                placeholder="Why this revision is changing"
              />
            </label>
          </div>
          <div className="qms-audit-programme-drawer__footer">
            <button
              type="button"
              className="is-secondary"
              onClick={() => setShowProgrammeEdit(false)}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="is-primary"
              disabled={
                updateProgrammeMutation.isPending ||
                editReason.trim().length < 3
              }
            >
              Save programme
            </button>
          </div>
        </form>
      </Drawer>

      <Drawer
        title={
          areaAuditsFocus
            ? `${areaAuditsFocus.areaLabel} · ${areaAuditsFocus.items.length} audits`
            : "Area audits"
        }
        isOpen={Boolean(areaAuditsFocus)}
        onClose={() => setAreaAuditsFocus(null)}
        side="right"
        panelClassName="qms-audit-programme-drawer"
      >
        {areaAuditsFocus ? (
          <>
            <div className="qms-audit-programme-drawer__body">
              <p className="qms-audit-programme-flow__drawer-note is-compact">
                {areaAuditsFocus.items.length} planned audits · expand a month,
                then open an audit.
              </p>
              <div className="qms-programme-area-audit-list">
                {groupAreaAuditsByMonth(areaAuditsFocus.items).map(
                  (group, index) => (
                    <details
                      key={`${group.month}:${group.label}`}
                      className="qms-programme-area-month"
                      open={index === 0}
                    >
                      <summary>
                        <span>
                          <strong>{group.label}</strong>
                          <small>
                            {group.items.length} audit
                            {group.items.length === 1 ? "" : "s"}
                          </small>
                        </span>
                        <ChevronRight size={15} aria-hidden />
                      </summary>
                      <ul className="qms-programme-area-month__tiles">
                        {group.items.map((item) => {
                          const itemEditable =
                            canManage &&
                            editableProgrammeIds.has(item.programme_id);
                          const identity = programmeItemIdentity(item);
                          return (
                            <li key={item.id}>
                              <button
                                type="button"
                                className="qms-programme-area-tile__main"
                                onClick={() => {
                                  setSelectedId(item.programme_id);
                                  openRequirementDrawer(item, false);
                                }}
                                title={`Open ${identity}`}
                              >
                                <strong>{identity}</strong>
                                <small>
                                  {programmeItemWindowLabel(
                                    item,
                                    selected?.programme_year || year,
                                  )}
                                  {item.state ? ` · ${human(item.state)}` : ""}
                                </small>
                              </button>
                              <div className="qms-programme-area-tile__actions">
                                <button
                                  type="button"
                                  className="is-icon"
                                  title={`View ${identity}`}
                                  aria-label={`View ${identity}`}
                                  onClick={() => {
                                    setSelectedId(item.programme_id);
                                    openRequirementDrawer(item, false);
                                  }}
                                >
                                  <Info size={14} />
                                </button>
                                {itemEditable ? (
                                  <button
                                    type="button"
                                    className="is-icon"
                                    title={`Edit ${identity}`}
                                    aria-label={`Edit ${identity}`}
                                    onClick={() => {
                                      setSelectedId(item.programme_id);
                                      openRequirementDrawer(item, true);
                                    }}
                                  >
                                    <Pencil size={14} />
                                  </button>
                                ) : null}
                                {itemEditable ? (
                                  <button
                                    type="button"
                                    className="is-icon is-danger"
                                    title={`Delete ${identity}`}
                                    aria-label={`Delete ${identity}`}
                                    onClick={() => openRemoveAudit(item)}
                                  >
                                    <Trash2 size={14} />
                                  </button>
                                ) : null}
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                    </details>
                  ),
                )}
              </div>
            </div>
            <div className="qms-audit-programme-drawer__footer">
              <button
                type="button"
                className="is-secondary"
                onClick={() => setAreaAuditsFocus(null)}
              >
                Close
              </button>
            </div>
          </>
        ) : null}
      </Drawer>

      <Drawer
        title={requirementEditMode ? "Edit audit" : "Audit details"}
        isOpen={Boolean(requirementFocus)}
        onClose={() => {
          setRequirementFocus(null);
          setRequirementEditMode(false);
        }}
        side="right"
        panelClassName="qms-audit-programme-drawer"
      >
        {requirementFocus && !requirementEditMode ? (
          <>
            <div className="qms-audit-programme-drawer__body">
              <div className="qms-audit-programme-flow__drawer-summary">
                <dl>
                  <div>
                    <dt>Entity</dt>
                    <dd>
                      {requirementFocus.auditable_entity?.display_label || "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>Window</dt>
                    <dd>
                      {dateLabel(requirementFocus.target_start)} →{" "}
                      {dateLabel(requirementFocus.target_end)}
                    </dd>
                  </div>
                  <div>
                    <dt>Recurrence</dt>
                    <dd>
                      {requirementFocus.recurrence === "FIXED_DATES"
                        ? (requirementFocus.fixed_dates || [])
                            .map((value) =>
                              fixedDateLabel(
                                value,
                                selected?.programme_year || year,
                              ),
                            )
                            .join(" · ")
                        : human(requirementFocus.recurrence)}
                    </dd>
                  </div>
                  <div>
                    <dt>Working hours</dt>
                    <dd>
                      {String(requirementFocus.default_start_time).slice(0, 5)}–
                      {String(requirementFocus.default_end_time).slice(0, 5)} ·{" "}
                      {requirementFocus.default_duration_days} day(s)
                    </dd>
                  </div>
                  <div>
                    <dt>Scope</dt>
                    <dd>{requirementFocus.scope || "—"}</dd>
                  </div>
                  <div>
                    <dt>Purpose</dt>
                    <dd>{requirementFocus.purpose || "—"}</dd>
                  </div>
                  <div>
                    <dt>Criteria</dt>
                    <dd>{linesOf(requirementFocus.criteria) || "—"}</dd>
                  </div>
                  <div>
                    <dt>Schedule</dt>
                    <dd>
                      {linksByItem.get(requirementFocus.id)?.scheduled_count
                        ? `${linksByItem.get(requirementFocus.id)?.scheduled_count} date(s) on the planner`
                        : requirementFocus.recurrence === "FIXED_DATES"
                          ? "Generated automatically when published"
                          : "Not scheduled"}
                    </dd>
                  </div>
                  {(linksByItem.get(requirementFocus.id)?.occurrences || [])
                    .length ? (
                    <div className="is-wide">
                      <dt>Scheduled dates</dt>
                      <dd className="qms-programme-occurrence-list">
                        {(
                          linksByItem.get(requirementFocus.id)?.occurrences ||
                          []
                        ).map((occurrence) => (
                          <span key={occurrence.occurrence_key}>
                            <strong>
                              {dateLabel(occurrence.scheduled_date)}
                            </strong>
                            {occurrence.adjusted ? (
                              <small>
                                {occurrence.adjustment_message ||
                                  "Moved to the next working day"}
                              </small>
                            ) : null}
                          </span>
                        ))}
                      </dd>
                    </div>
                  ) : null}
                </dl>
              </div>
            </div>
            <div className="qms-audit-programme-drawer__footer">
              <button
                type="button"
                className="is-secondary"
                onClick={() => {
                  setRequirementFocus(null);
                  setRequirementEditMode(false);
                }}
              >
                Close
              </button>
              {canManage &&
              editableProgrammeIds.has(requirementFocus.programme_id) ? (
                <button
                  type="button"
                  className="is-danger"
                  onClick={() => openRemoveAudit(requirementFocus)}
                >
                  <Trash2 size={14} /> Delete
                </button>
              ) : null}
              {canManage &&
              editableProgrammeIds.has(requirementFocus.programme_id) ? (
                <button
                  type="button"
                  className="is-primary"
                  onClick={() => openRequirementDrawer(requirementFocus, true)}
                >
                  <Pencil size={14} /> Edit
                </button>
              ) : null}
            </div>
          </>
        ) : null}
        {requirementFocus && requirementEditMode ? (
          <form
            className="qms-audit-programme__form qms-audit-programme-flow__create"
            onSubmit={(event) => {
              event.preventDefault();
              updateItemMutation.mutate();
            }}
          >
            <div className="qms-audit-programme-drawer__body">
              <label className="is-wide">
                <span>Title</span>
                <input
                  required
                  minLength={3}
                  value={editItemForm.title}
                  onChange={(event) =>
                    setEditItemForm((current) => ({
                      ...current,
                      title: event.target.value,
                    }))
                  }
                />
              </label>
              <HistoryTextarea
                label="Purpose"
                rows={2}
                value={editItemForm.purpose}
                options={purposeHistoryEdit.options}
                listId={`${purposeHistoryEdit.listId}-edit`}
                onRemember={purposeHistoryEdit.remember}
                onChange={(purpose) =>
                  setEditItemForm((current) => ({ ...current, purpose }))
                }
              />
              <HistoryTextarea
                label="Scope"
                rows={3}
                required
                value={editItemForm.scope}
                options={scopeHistoryEdit.options}
                listId={`${scopeHistoryEdit.listId}-edit`}
                onRemember={scopeHistoryEdit.remember}
                onChange={(scope) =>
                  setEditItemForm((current) => ({ ...current, scope }))
                }
              />
              <HistoryTextarea
                label="Criteria"
                rows={3}
                value={editItemForm.criteria}
                options={criteriaHistoryEdit.options}
                listId={`${criteriaHistoryEdit.listId}-edit`}
                onRemember={criteriaHistoryEdit.remember}
                onChange={(criteria) =>
                  setEditItemForm((current) => ({ ...current, criteria }))
                }
              />
              <label>
                <span>Frequency</span>
                <select
                  value={editItemForm.recurrence}
                  onChange={(event) =>
                    setEditItemForm((current) => ({
                      ...current,
                      recurrence: event.target
                        .value as AuditProgrammeRecurrence,
                    }))
                  }
                >
                  {RECURRENCES.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Mandatory surveillance</span>
                <input
                  type="checkbox"
                  checked={editItemForm.mandatory_surveillance}
                  onChange={(event) =>
                    setEditItemForm((current) => ({
                      ...current,
                      mandatory_surveillance: event.target.checked,
                    }))
                  }
                />
              </label>
              {editItemForm.recurrence === "FIXED_DATES" ? (
                <fieldset className="is-wide qms-programme-date-pattern">
                  <legend>Dates each calendar year</legend>
                  {editItemForm.fixed_dates.map((value, index) => (
                    <div
                      className="qms-programme-date-pattern__row"
                      key={`edit-fixed-date-${index}`}
                    >
                      <input
                        required
                        type="date"
                        min={`${selected?.programme_year || year}-01-01`}
                        max={`${selected?.programme_year || year}-12-31`}
                        value={value}
                        onChange={(event) =>
                          setEditItemForm((current) => ({
                            ...current,
                            fixed_dates: current.fixed_dates.map(
                              (entry, entryIndex) =>
                                entryIndex === index
                                  ? event.target.value
                                  : entry,
                            ),
                          }))
                        }
                      />
                      <small>{weekendAdjustment(value) || "Working day"}</small>
                      {editItemForm.fixed_dates.length > 1 ? (
                        <button
                          type="button"
                          className="is-icon is-danger"
                          aria-label={`Remove date ${index + 1}`}
                          onClick={() =>
                            setEditItemForm((current) => ({
                              ...current,
                              fixed_dates: current.fixed_dates.filter(
                                (_, entryIndex) => entryIndex !== index,
                              ),
                            }))
                          }
                        >
                          <Trash2 size={14} />
                        </button>
                      ) : null}
                    </div>
                  ))}
                  <button
                    type="button"
                    className="is-secondary qms-programme-date-pattern__add"
                    onClick={() =>
                      setEditItemForm((current) => ({
                        ...current,
                        fixed_dates: [...current.fixed_dates, ""],
                      }))
                    }
                  >
                    <Plus size={14} /> Add another date
                  </button>
                </fieldset>
              ) : (
                <>
                  <label>
                    <span>Target start</span>
                    <input
                      type="date"
                      value={editItemForm.target_start}
                      onChange={(event) =>
                        setEditItemForm((current) => ({
                          ...current,
                          target_start: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label>
                    <span>Target end</span>
                    <input
                      type="date"
                      value={editItemForm.target_end}
                      onChange={(event) =>
                        setEditItemForm((current) => ({
                          ...current,
                          target_end: event.target.value,
                        }))
                      }
                    />
                  </label>
                </>
              )}
              <label>
                <span>Start time</span>
                <input
                  type="time"
                  min="09:00"
                  max="17:00"
                  required
                  value={editItemForm.default_start_time}
                  onChange={(event) =>
                    setEditItemForm((current) => ({
                      ...current,
                      default_start_time: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                <span>End time</span>
                <input
                  type="time"
                  min="09:00"
                  max="17:00"
                  required
                  value={editItemForm.default_end_time}
                  onChange={(event) =>
                    setEditItemForm((current) => ({
                      ...current,
                      default_end_time: event.target.value,
                    }))
                  }
                />
              </label>
              <ProgrammeLocationSelect
                id="programme-edit-location"
                value={editItemForm.default_location}
                locations={locations}
                onChange={(default_location) =>
                  setEditItemForm((current) => ({
                    ...current,
                    default_location,
                  }))
                }
                required={["FACILITY", "STATION"].includes(
                  requirementFocus.auditable_entity?.entity_type || "",
                )}
              />
              <label>
                <span>Lead auditor</span>
                <select
                  value={editItemForm.lead_auditor_user_id}
                  onChange={(event) =>
                    setEditItemForm((current) => ({
                      ...current,
                      lead_auditor_user_id: event.target.value,
                      observer_auditor_user_id:
                        current.observer_auditor_user_id === event.target.value
                          ? ""
                          : current.observer_auditor_user_id,
                      supporting_auditor_user_ids: withoutLeadAuditor(
                        current.supporting_auditor_user_ids,
                        event.target.value,
                        current.observer_auditor_user_id,
                      ),
                    }))
                  }
                >
                  <option value="">Assign later</option>
                  {leadAuditorOptions.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.full_name}
                    </option>
                  ))}
                </select>
                {leadOptionsAreFallbackAuditors ? (
                  <small>
                    No lead-auditor privilege holders — auditors may lead this
                    planned audit.
                  </small>
                ) : null}
              </label>
              <ProgrammeObserverSelect
                id="programme-edit-observer"
                people={auditorOptions}
                leadAuditorUserId={editItemForm.lead_auditor_user_id}
                supportingAuditorUserIds={
                  editItemForm.supporting_auditor_user_ids
                }
                value={editItemForm.observer_auditor_user_id}
                onChange={(observer_auditor_user_id) =>
                  setEditItemForm((current) => ({
                    ...current,
                    observer_auditor_user_id,
                    supporting_auditor_user_ids: withoutLeadAuditor(
                      current.supporting_auditor_user_ids,
                      current.lead_auditor_user_id,
                      observer_auditor_user_id,
                    ),
                  }))
                }
              />
              <label>
                <span>Auditee representative</span>
                <select
                  value={editItemForm.auditee_user_id}
                  onChange={(event) =>
                    setEditItemForm((current) => ({
                      ...current,
                      auditee_user_id: event.target.value,
                    }))
                  }
                >
                  <option value="">Use selected area</option>
                  {people.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.full_name}
                    </option>
                  ))}
                </select>
              </label>
              <SupportingAuditorPicker
                id="programme-edit-supporting-auditors"
                people={auditorOptions}
                leadAuditorUserId={editItemForm.lead_auditor_user_id}
                excludedUserIds={[editItemForm.observer_auditor_user_id]}
                value={editItemForm.supporting_auditor_user_ids}
                onChange={(supporting_auditor_user_ids) =>
                  setEditItemForm((current) => ({
                    ...current,
                    supporting_auditor_user_ids,
                  }))
                }
              />
              <label className="is-wide">
                <span>Change reason</span>
                <input
                  required
                  minLength={3}
                  value={editReason}
                  onChange={(event) => setEditReason(event.target.value)}
                />
              </label>
            </div>
            <div className="qms-audit-programme-drawer__footer">
              <button
                type="button"
                className="is-secondary"
                onClick={() => {
                  setRequirementFocus(null);
                  setRequirementEditMode(false);
                }}
              >
                Cancel
              </button>
              {canManage &&
              editableProgrammeIds.has(requirementFocus.programme_id) ? (
                <button
                  type="button"
                  className="is-danger"
                  disabled={updateItemMutation.isPending}
                  onClick={() => openRemoveAudit(requirementFocus)}
                >
                  <Trash2 size={14} /> Delete
                </button>
              ) : null}
              <button
                type="submit"
                className="is-primary"
                disabled={
                  updateItemMutation.isPending || editReason.trim().length < 3
                }
              >
                Save
              </button>
            </div>
          </form>
        ) : null}
      </Drawer>

      <Drawer
        title={universeEditMode ? "Edit audit area" : "Audit area details"}
        isOpen={Boolean(universeFocus)}
        onClose={() => {
          setUniverseFocus(null);
          setUniverseEditMode(false);
        }}
        side="right"
        panelClassName="qms-audit-programme-drawer"
      >
        {universeFocus && !universeEditMode ? (
          <>
            <div className="qms-audit-programme-drawer__body">
              <div className="qms-audit-programme-flow__drawer-summary">
                <dl>
                  <div>
                    <dt>Type</dt>
                    <dd>{human(universeFocus.entity_type)}</dd>
                  </div>
                  <div>
                    <dt>Programme use</dt>
                    <dd>
                      {!universeFocus.programme_kind ||
                      universeFocus.programme_kind === "BOTH"
                        ? "Internal & external"
                        : human(universeFocus.programme_kind)}
                    </dd>
                  </div>
                  <div>
                    <dt>Source</dt>
                    <dd>
                      {universeFocus.origin === "PLATFORM_STANDARD"
                        ? "Portal standard · tenant copy"
                        : universeFocus.entity_type === "AIRCRAFT"
                          ? "Fleet register"
                          : "Tenant-defined"}
                    </dd>
                  </div>
                  {universeFocus.aircraft ? (
                    <>
                      <div>
                        <dt>Tail number</dt>
                        <dd>{universeFocus.aircraft.tail_number}</dd>
                      </div>
                      <div>
                        <dt>Model</dt>
                        <dd>
                          {universeFocus.aircraft.model || "Not recorded"}
                        </dd>
                      </div>
                      <div>
                        <dt>MSN</dt>
                        <dd>{universeFocus.aircraft.msn}</dd>
                      </div>
                    </>
                  ) : null}
                  <div>
                    <dt>Risk</dt>
                    <dd>{human(universeFocus.risk_classification)}</dd>
                  </div>
                  <div>
                    <dt>Regulatory criticality</dt>
                    <dd>{human(universeFocus.regulatory_criticality)}</dd>
                  </div>
                  <div>
                    <dt>Surveillance interval</dt>
                    <dd>
                      {universeFocus.surveillance_interval_days ?? "—"} days
                    </dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{universeFocus.active ? "Active" : "Inactive"}</dd>
                  </div>
                  {universeFocus.notes ? (
                    <div>
                      <dt>Notes</dt>
                      <dd>{universeFocus.notes}</dd>
                    </div>
                  ) : null}
                  {universeFocus.source_route ? (
                    <div>
                      <dt>Source link</dt>
                      <dd>
                        <Link to={universeFocus.source_route}>
                          Open source record
                        </Link>
                      </dd>
                    </div>
                  ) : null}
                </dl>
              </div>
            </div>
            <div className="qms-audit-programme-drawer__footer">
              <button
                type="button"
                className="is-secondary"
                onClick={() => {
                  setUniverseFocus(null);
                  setUniverseEditMode(false);
                }}
              >
                Close
              </button>
              {canManage ? (
                <button
                  type="button"
                  className="is-primary"
                  onClick={() => openUniverseDrawer(universeFocus, true)}
                >
                  <Pencil size={14} /> Edit
                </button>
              ) : null}
            </div>
          </>
        ) : null}
        {universeFocus && universeEditMode ? (
          <form
            className="qms-audit-programme__form qms-audit-programme-flow__create"
            onSubmit={(event) => {
              event.preventDefault();
              updateUniverseMutation.mutate();
            }}
          >
            <div className="qms-audit-programme-drawer__body">
              <p className="qms-audit-programme-flow__drawer-note">
                Changes apply only to this tenant, including changes to a
                portal-standard row.
              </p>
              <label>
                <span>Use in</span>
                <select
                  value={editUniverseForm.programme_kind}
                  onChange={(event) =>
                    setEditUniverseForm((current) => ({
                      ...current,
                      programme_kind: event.target
                        .value as AuditUniverseProgrammeKind,
                    }))
                  }
                >
                  <option value="INTERNAL">Internal audit programmes</option>
                  <option value="EXTERNAL">External audit programmes</option>
                  <option value="BOTH">Internal and external programmes</option>
                </select>
              </label>
              {universeFocus.entity_type === "AIRCRAFT" &&
              universeFocus.aircraft ? (
                <div className="qms-audit-area-aircraft is-wide">
                  <Plane size={18} aria-hidden="true" />
                  <span>
                    <small>Tail number</small>
                    <strong>{universeFocus.aircraft.tail_number}</strong>
                  </span>
                  <span>
                    <small>Model</small>
                    <strong>
                      {universeFocus.aircraft.model || "Not recorded"}
                    </strong>
                  </span>
                  <span>
                    <small>MSN</small>
                    <strong>{universeFocus.aircraft.msn}</strong>
                  </span>
                </div>
              ) : (
                <label className="is-wide">
                  <span>Audit area name</span>
                  <input
                    required
                    minLength={2}
                    value={editUniverseForm.display_label}
                    onChange={(event) =>
                      setEditUniverseForm((current) => ({
                        ...current,
                        display_label: event.target.value,
                      }))
                    }
                  />
                </label>
              )}
              <label>
                <span>Risk</span>
                <select
                  value={editUniverseForm.risk_classification}
                  onChange={(event) =>
                    setEditUniverseForm((current) => ({
                      ...current,
                      risk_classification: event.target.value as AuditRiskLevel,
                    }))
                  }
                >
                  {RISKS.map((value) => (
                    <option key={value} value={value}>
                      {human(value)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Regulatory criticality</span>
                <select
                  value={editUniverseForm.regulatory_criticality}
                  onChange={(event) =>
                    setEditUniverseForm((current) => ({
                      ...current,
                      regulatory_criticality: event.target
                        .value as AuditRiskLevel,
                    }))
                  }
                >
                  {RISKS.map((value) => (
                    <option key={value} value={value}>
                      {human(value)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Maximum interval</span>
                <select
                  value={editUniverseForm.surveillance_interval_days}
                  onChange={(event) =>
                    setEditUniverseForm((current) => ({
                      ...current,
                      surveillance_interval_days: event.target.value,
                    }))
                  }
                >
                  <option value="90">Every 3 months</option>
                  <option value="183">Every 6 months</option>
                  <option value="365">Every year</option>
                  <option value="730">Every 2 years</option>
                </select>
              </label>
              <label className="is-checkbox">
                <input
                  type="checkbox"
                  checked={editUniverseForm.mandatory_surveillance}
                  onChange={(event) =>
                    setEditUniverseForm((current) => ({
                      ...current,
                      mandatory_surveillance: event.target.checked,
                    }))
                  }
                />
                <span>Mandatory programme coverage</span>
              </label>
              <label className="is-checkbox">
                <input
                  type="checkbox"
                  checked={editUniverseForm.active}
                  onChange={(event) =>
                    setEditUniverseForm((current) => ({
                      ...current,
                      active: event.target.checked,
                    }))
                  }
                />
                <span>Available for future programmes</span>
              </label>
              <label className="is-wide">
                <span>Notes</span>
                <textarea
                  rows={3}
                  value={editUniverseForm.notes}
                  onChange={(event) =>
                    setEditUniverseForm((current) => ({
                      ...current,
                      notes: event.target.value,
                    }))
                  }
                />
              </label>
            </div>
            <div className="qms-audit-programme-drawer__footer">
              <button
                type="button"
                className="is-secondary"
                onClick={() => {
                  setUniverseFocus(null);
                  setUniverseEditMode(false);
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="is-primary"
                disabled={updateUniverseMutation.isPending}
              >
                Save
              </button>
            </div>
          </form>
        ) : null}
      </Drawer>

      <Drawer
        title="Remove audit area?"
        isOpen={Boolean(removeUniverseTarget)}
        onClose={() => setRemoveUniverseTarget(null)}
        side="right"
        panelClassName="qms-audit-programme-drawer qms-audit-programme-drawer--confirm"
      >
        {removeUniverseTarget ? (
          <>
            <div className="qms-audit-programme-drawer__body">
              <div className="qms-audit-area-remove-warning is-wide">
                <AlertTriangle size={19} aria-hidden="true" />
                <div>
                  <strong>{removeUniverseTarget.display_label}</strong>
                  <p>
                    This removes the row from this tenant's future programme
                    choices. Existing approved programme and audit history stays
                    intact.
                  </p>
                </div>
              </div>
            </div>
            <div className="qms-audit-programme-drawer__footer">
              <button
                type="button"
                className="is-secondary"
                onClick={() => setRemoveUniverseTarget(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="is-danger"
                disabled={removeUniverseMutation.isPending}
                onClick={() => removeUniverseMutation.mutate()}
              >
                <Trash2 size={14} /> Remove from tenant
              </button>
            </div>
          </>
        ) : null}
      </Drawer>

      <Drawer
        title="Schedule on Calendar"
        isOpen={Boolean(scheduleTarget)}
        onClose={() => setScheduleTarget(null)}
        side="right"
        panelClassName="qms-audit-programme-drawer qms-audit-programme-drawer--schedule"
      >
        {scheduleTarget ? (
          <QmsAuditProgrammeSchedulePanel
            amoCode={amoCode}
            programmeId={scheduleTarget.programmeId}
            itemId={scheduleTarget.itemId}
            variant="embedded"
            onCancel={() => setScheduleTarget(null)}
            onScheduled={() => {
              /* stay open so user can hand off to Calendar from success panel */
            }}
          />
        ) : null}
      </Drawer>
      <QmsCalendarSyncDialog open={calendarSyncOpen} onClose={() => setCalendarSyncOpen(false)} />
    </div>
  );
};

export default QmsAuditProgrammePageV2;
