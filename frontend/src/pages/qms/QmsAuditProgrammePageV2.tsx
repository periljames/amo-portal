import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CalendarClock,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  Info,
  Library,
  Pencil,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { hasQmsRolePermission } from "../../app/routeGuards";
import DataTableShell from "../../components/shared/DataTableShell";
import Drawer from "../../components/shared/Drawer";
import {
  addAuditProgrammeItem,
  createAuditProgramme,
  createAuditProgrammeAmendment,
  createAuditUniverseItem,
  getAuditProgramme,
  getAuditProgrammeOptimizer,
  listedReadinessOf,
  listAuditProgrammeScheduleLinks,
  listAuditProgrammeSchedulingQueue,
  listAuditProgrammes,
  listAuditUniverse,
  readinessOf,
  rebuildAuditProgrammeOptimizer,
  transitionAuditProgramme,
  updateAuditProgramme,
  updateAuditProgrammeItem,
  updateAuditUniverseItem,
  type AuditAssuranceModel,
  type AuditProgramme,
  type AuditProgrammeItem,
  type AuditProgrammeList,
  type AuditProgrammeStatus,
  type AuditRiskLevel,
  type AuditUniverseEntityType,
  type AuditUniverseItem,
} from "../../services/qmsAuditProgramme";
import QmsAuditProgrammeSchedulePanel from "./QmsAuditProgrammeSchedulePanel";
import {
  PROGRAMME_KINDS,
  availableProgrammeKinds,
  canCreateAnotherProgramme,
  headProgrammesForYear,
  programmeDisplayLabel,
  programmeKindTitle,
  programmePortfolioSummary,
  programmeStatusHint,
  type ProgrammeKind,
} from "./qmsAuditProgrammeDisplay";
import "../../styles/qms-audit-programme.css";
import "../../styles/qms-audit-programme-workflow.css";
import "../../styles/qms-audit-programme-polish.css";
import "../../styles/qms-assurance-cta-hierarchy.css";

const AUDIT_SUBJECTS = [
  "INTERNAL", "DEPARTMENTAL", "TECHNICAL", "WORK_PACK", "SUPPLIER", "CONTRACTED_FUNCTION",
  "FACILITY", "PERSONNEL", "PRODUCT", "PROCESS", "REGULATORY", "SPECIAL", "REACTIVE", "FOLLOW_UP",
] as const;
const RECURRENCES = ["ONE_TIME", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL"] as const;
const DRIVERS = [
  "REGULATORY_REQUIREMENT", "PROCESS_IMPORTANCE", "CHANGE", "PRIOR_FINDINGS",
  "KPI_PERFORMANCE", "SAFETY_RISK", "SUPPLIER_PERFORMANCE",
] as const;
const UNIVERSE_TYPES: AuditUniverseEntityType[] = [
  "DEPARTMENT", "FACILITY", "STATION", "SUPPLIER", "CONTRACTOR", "PROCESS",
  "CAPABILITY", "APPROVAL_RATING", "AIRCRAFT_TYPE", "PERSONNEL_GROUP", "OTHER",
];
const RISKS: AuditRiskLevel[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const SCHEDULABLE_RECURRENCES = new Set(["ONE_TIME", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL"]);
const METHODOLOGY_PILLARS: Array<{ id: AuditAssuranceModel; label: string; hint: string }> = [
  { id: "COMPLIANCE", label: "Compliance", hint: "Regulatory / contractual floor" },
  { id: "RISK", label: "Risk", hint: "Inherent & residual exposure" },
  { id: "PERFORMANCE", label: "Performance", hint: "Findings, trends, KPIs" },
  { id: "HYBRID", label: "Hybrid", hint: "Combines compliance, risk, and performance" },
];

type WorkspaceTab = "requirements" | "universe" | "readiness";

function human(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateLabel(value?: string | null): string {
  if (!value) return "Not set";
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function normalizeAssuranceModel(value?: string | null): AuditAssuranceModel {
  const normalized = String(value || "HYBRID").toUpperCase();
  if (normalized === "COMPLIANCE" || normalized === "PERFORMANCE" || normalized === "RISK") return normalized;
  return "HYBRID";
}

function methodologyLabel(model?: string | null): string {
  const normalized = normalizeAssuranceModel(model);
  if (normalized === "COMPLIANCE") return "Compliance-based";
  if (normalized === "RISK") return "Risk-based";
  if (normalized === "PERFORMANCE") return "Performance-based";
  return "Hybrid";
}

function statusTone(status: string): "good" | "warn" | "muted" | "neutral" | "danger" {
  const value = status.toUpperCase();
  if (["ACTIVE", "SCHEDULED", "COMPLETED", "APPROVED"].includes(value)) return "good";
  if (["UNDER_REVIEW", "PLANNED", "FOLLOW_UP_REQUIRED"].includes(value)) return "warn";
  if (["DEFERRED", "CANCELLED", "SUPERSEDED", "CLOSED"].includes(value)) return "muted";
  if (["DRAFT"].includes(value)) return "neutral";
  return "neutral";
}

function linesOf(values?: Array<string | Record<string, unknown>> | null): string {
  return (values || [])
    .map((entry) => (typeof entry === "string" ? entry : JSON.stringify(entry)))
    .filter(Boolean)
    .join("\n");
}

function programmeEditable(status?: AuditProgrammeStatus | null): boolean {
  return status === "DRAFT" || status === "UNDER_REVIEW";
}

function transitionTargets(status: AuditProgrammeStatus): AuditProgrammeStatus[] {
  if (status === "DRAFT") return ["UNDER_REVIEW"];
  if (status === "UNDER_REVIEW") return ["DRAFT", "APPROVED"];
  if (status === "APPROVED") return ["ACTIVE", "SUPERSEDED"];
  if (status === "ACTIVE") return ["SUPERSEDED", "CLOSED"];
  return [];
}

function forwardTransition(from: AuditProgrammeStatus, to: AuditProgrammeStatus): boolean {
  const order: AuditProgrammeStatus[] = ["DRAFT", "UNDER_REVIEW", "APPROVED", "ACTIVE", "CLOSED"];
  return order.indexOf(to) > order.indexOf(from);
}

const QmsAuditProgrammePageV2: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const queryClient = useQueryClient();
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("requirements");
  const [showCreate, setShowCreate] = useState(false);
  const [showProgrammeDetail, setShowProgrammeDetail] = useState(false);
  const [showMethodologyInfo, setShowMethodologyInfo] = useState(false);
  const [showProgrammeEdit, setShowProgrammeEdit] = useState(false);
  const [cancelItemReason, setCancelItemReason] = useState("");
  const [cancelItemTarget, setCancelItemTarget] = useState<AuditProgrammeItem | null>(null);
  const [showRequirement, setShowRequirement] = useState(false);
  const [requirementFocus, setRequirementFocus] = useState<AuditProgrammeItem | null>(null);
  const [requirementEditMode, setRequirementEditMode] = useState(false);
  const [showUniverseCreate, setShowUniverseCreate] = useState(false);
  const [universeFocus, setUniverseFocus] = useState<AuditUniverseItem | null>(null);
  const [universeEditMode, setUniverseEditMode] = useState(false);
  const [scheduleTarget, setScheduleTarget] = useState<{ programmeId: string; itemId: string } | null>(null);
  const [actionReason, setActionReason] = useState("");
  const [editReason, setEditReason] = useState("");
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const plannerHref = `/maintenance/${encodeURIComponent(amoCode)}/quality/calendar/week`;

  const programmesQuery = useQuery({
    queryKey: ["qms-audit-programmes", amoCode, year],
    queryFn: ({ signal }) => listAuditProgrammes(amoCode, year, signal),
    staleTime: 5_000,
  });
  const universeQuery = useQuery({
    queryKey: ["qms-audit-universe", amoCode],
    queryFn: ({ signal }) => listAuditUniverse(amoCode, signal),
    staleTime: 10_000,
  });
  const queueQuery = useQuery({
    queryKey: ["qms-audit-programme-scheduling-queue", amoCode],
    queryFn: ({ signal }) => listAuditProgrammeSchedulingQueue(amoCode, signal),
    enabled: canManage,
    staleTime: 5_000,
  });
  const programmes = useMemo(() => programmesQuery.data?.items || [], [programmesQuery.data?.items]);
  const visibleProgrammes = useMemo(() => headProgrammesForYear(programmes), [programmes]);
  const creatableKinds = useMemo(() => availableProgrammeKinds(programmes), [programmes]);
  const allowCreateProgramme = canManage && canCreateAnotherProgramme(programmes);
  const selectedProgrammeId = selectedId || visibleProgrammes[0]?.id || null;
  const detailQuery = useQuery({
    queryKey: ["qms-audit-programme", amoCode, selectedProgrammeId],
    queryFn: ({ signal }) => getAuditProgramme(amoCode, selectedProgrammeId as string, signal),
    enabled: Boolean(selectedProgrammeId),
    staleTime: 3_000,
  });
  const optimizerQuery = useQuery({
    queryKey: ["qms-audit-programme-optimizer", amoCode, selectedProgrammeId],
    queryFn: ({ signal }) => getAuditProgrammeOptimizer(amoCode, selectedProgrammeId as string, signal),
    enabled: Boolean(selectedProgrammeId),
    staleTime: 3_000,
  });
  const scheduleLinksQuery = useQuery({
    queryKey: ["qms-audit-programme-schedule-links", amoCode, selectedProgrammeId],
    queryFn: ({ signal }) => listAuditProgrammeScheduleLinks(amoCode, selectedProgrammeId as string, signal),
    enabled: Boolean(selectedProgrammeId),
    staleTime: 3_000,
  });
  const selected = detailQuery.data;
  const optimizer = optimizerQuery.data;
  const readiness = readinessOf(selected, optimizer);

  const [programmeForm, setProgrammeForm] = useState({
    programme_kind: "INTERNAL" as ProgrammeKind,
    title: programmeKindTitle("INTERNAL", currentYear),
    period_start: `${currentYear}-01-01`,
    period_end: `${currentYear}-12-31`,
    objectives: "Maintain compliance while increasing surveillance where risk or performance evidence warrants it.",
    regulatory_basis: "",
  });
  const [itemForm, setItemForm] = useState({
    universe_item_id: "",
    audit_type: "PROCESS",
    title: "",
    purpose: "",
    scope: "",
    criteria: "",
    recurrence: "ANNUAL",
    driver: "PROCESS_IMPORTANCE" as (typeof DRIVERS)[number],
    mandatory_surveillance: false,
    target_start: "",
    target_end: "",
  });
  const [universeForm, setUniverseForm] = useState({
    entity_type: "DEPARTMENT" as AuditUniverseEntityType,
    display_label: "",
    source_owner_module: "",
    source_type: "DEPARTMENT",
    source_id: "",
    source_route: "",
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
    recurrence: "ANNUAL",
    mandatory_surveillance: false,
    target_start: "",
    target_end: "",
  });
  const [editUniverseForm, setEditUniverseForm] = useState({
    display_label: "",
    source_route: "",
    risk_classification: "MEDIUM" as AuditRiskLevel,
    regulatory_criticality: "MEDIUM" as AuditRiskLevel,
    surveillance_interval_days: "",
    mandatory_surveillance: false,
    active: true,
    notes: "",
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

  const openRequirementDrawer = (item: AuditProgrammeItem, edit: boolean) => {
    setCancelItemTarget(null);
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
    });
    setEditReason("");
  };

  const openUniverseDrawer = (item: AuditUniverseItem, edit: boolean) => {
    setUniverseFocus(item);
    setUniverseEditMode(edit);
    setEditUniverseForm({
      display_label: item.display_label,
      source_route: item.source_route || "",
      risk_classification: item.risk_classification,
      regulatory_criticality: item.regulatory_criticality,
      surveillance_interval_days: item.surveillance_interval_days != null ? String(item.surveillance_interval_days) : "",
      mandatory_surveillance: item.mandatory_surveillance,
      active: item.active,
      notes: item.notes || "",
    });
  };

  const invalidateProgramme = async (programmeId?: string) => {
    const id = programmeId || selectedProgrammeId;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-programmes", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-programme", amoCode, id] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-programme-optimizer", amoCode, id] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-programme-scheduling-queue", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-programme-schedule-links", amoCode, id] }),
    ]);
  };

  const createProgrammeMutation = useMutation({
    mutationFn: () =>
      createAuditProgramme(amoCode, {
        programme_year: year,
        programme_kind: programmeForm.programme_kind,
        title: programmeForm.title.trim(),
        objectives: programmeForm.objectives.split("\n").map((value) => value.trim()).filter(Boolean),
        regulatory_basis: programmeForm.regulatory_basis.split("\n").map((value) => value.trim()).filter(Boolean),
        period_start: programmeForm.period_start,
        period_end: programmeForm.period_end,
      }),
    onSuccess: async (programme) => {
      setSelectedId(programme.id);
      setShowCreate(false);
      setWorkspaceTab("requirements");
      await invalidateProgramme(programme.id);
    },
  });

  const updateProgrammeMutation = useMutation({
    mutationFn: () =>
      updateAuditProgramme(amoCode, selectedProgrammeId as string, {
        title: editProgrammeForm.title.trim(),
        objectives: editProgrammeForm.objectives.split("\n").map((value) => value.trim()).filter(Boolean),
        regulatory_basis: editProgrammeForm.regulatory_basis.split("\n").map((value) => value.trim()).filter(Boolean),
        period_start: editProgrammeForm.period_start,
        period_end: editProgrammeForm.period_end,
        reason: editReason.trim(),
      }),
    onSuccess: async (programme) => {
      setShowProgrammeEdit(false);
      setEditReason("");
      queryClient.setQueryData(["qms-audit-programme", amoCode, programme.id], programme);
      await invalidateProgramme(programme.id);
    },
  });

  const updateItemMutation = useMutation({
    mutationFn: () =>
      updateAuditProgrammeItem(amoCode, selectedProgrammeId as string, requirementFocus!.id, {
        title: editItemForm.title.trim(),
        purpose: editItemForm.purpose.trim() || null,
        scope: editItemForm.scope.trim(),
        criteria: editItemForm.criteria.split("\n").map((value) => value.trim()).filter(Boolean),
        recurrence: editItemForm.recurrence,
        mandatory_surveillance: editItemForm.mandatory_surveillance,
        target_start: editItemForm.target_start || null,
        target_end: editItemForm.target_end || null,
        reason: editReason.trim(),
      }),
    onSuccess: async () => {
      setRequirementFocus(null);
      setRequirementEditMode(false);
      setEditReason("");
      await invalidateProgramme();
    },
  });

  const cancelItemMutation = useMutation({
    mutationFn: (item: AuditProgrammeItem) =>
      updateAuditProgrammeItem(amoCode, selectedProgrammeId as string, item.id, {
        state: "CANCELLED",
        cancellation_reason: cancelItemReason.trim(),
        reason: cancelItemReason.trim(),
      }),
    onSuccess: async () => {
      setRequirementFocus(null);
      setRequirementEditMode(false);
      setCancelItemTarget(null);
      setCancelItemReason("");
      await invalidateProgramme();
    },
  });

  const updateUniverseMutation = useMutation({
    mutationFn: () =>
      updateAuditUniverseItem(amoCode, universeFocus!.id, {
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
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-universe", amoCode] });
      await invalidateProgramme();
    },
  });

  const optimizerMutation = useMutation({
    mutationFn: () => rebuildAuditProgrammeOptimizer(amoCode, selectedProgrammeId as string),
    onSuccess: async (result) => {
      queryClient.setQueryData(["qms-audit-programme-optimizer", amoCode, selectedProgrammeId], result);
      await invalidateProgramme();
    },
  });

  const transitionMutation = useMutation({
    mutationFn: (target: AuditProgrammeStatus) =>
      transitionAuditProgramme(amoCode, selectedProgrammeId as string, target, actionReason.trim()),
    onSuccess: (programme) => {
      setActionReason("");
      queryClient.setQueryData(["qms-audit-programme", amoCode, programme.id], programme);
      queryClient.setQueryData<AuditProgrammeList>(["qms-audit-programmes", amoCode, year], (current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) => (item.id === programme.id ? programme : item)),
            }
          : current,
      );
      void queryClient.invalidateQueries({ queryKey: ["qms-audit-programme-optimizer", amoCode, programme.id] });
    },
  });

  const amendmentMutation = useMutation({
    mutationFn: () => createAuditProgrammeAmendment(amoCode, selectedProgrammeId as string, actionReason.trim()),
    onSuccess: async (programme) => {
      setSelectedId(programme.id);
      setActionReason("");
      await invalidateProgramme(programme.id);
    },
  });

  const itemMutation = useMutation({
    mutationFn: () =>
      addAuditProgrammeItem(amoCode, selectedProgrammeId as string, {
        universe_item_id: itemForm.universe_item_id,
        audit_type: itemForm.audit_type,
        title: itemForm.title.trim(),
        purpose: itemForm.purpose.trim() || undefined,
        scope: itemForm.scope.trim(),
        criteria: itemForm.criteria.split("\n").map((value) => value.trim()).filter(Boolean),
        mandatory_surveillance: itemForm.mandatory_surveillance,
        recurrence: itemForm.recurrence,
        target_start: itemForm.target_start || undefined,
        target_end: itemForm.target_end || undefined,
        prioritization_basis: [{ driver: itemForm.driver, source: "HUMAN_ADDITION" }],
      }),
    onSuccess: async () => {
      setShowRequirement(false);
      setItemForm((current) => ({
        ...current,
        title: "",
        purpose: "",
        scope: "",
        criteria: "",
        target_start: "",
        target_end: "",
      }));
      await invalidateProgramme();
    },
  });

  const universeMutation = useMutation({
    mutationFn: () => {
      const label = universeForm.display_label.trim();
      const sourceId =
        universeForm.source_id.trim() ||
        label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") ||
        "coverage-area";
      return createAuditUniverseItem(amoCode, {
        entity_type: universeForm.entity_type,
        display_label: label,
        source_owner_module: universeForm.source_owner_module.trim() || "AUDIT_PROGRAMME",
        source_type: universeForm.source_type.trim() || universeForm.entity_type,
        source_id: sourceId,
        source_route: universeForm.source_route.trim() || undefined,
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
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-universe", amoCode] });
      setItemForm((current) => ({ ...current, universe_item_id: item.id }));
      setShowUniverseCreate(false);
      if (selectedProgrammeId && selected && ["DRAFT", "UNDER_REVIEW"].includes(selected.status)) {
        await rebuildAuditProgrammeOptimizer(amoCode, selectedProgrammeId);
        await invalidateProgramme();
      }
    },
  });

  const linksByItem = useMemo(
    () => new Map((scheduleLinksQuery.data?.items || []).map((link) => [link.programme_item_id, link])),
    [scheduleLinksQuery.data?.items],
  );
  const queue = (queueQuery.data?.items || []).filter(
    (item) => !selectedProgrammeId || item.programme_id === selectedProgrammeId,
  );
  const error =
    programmesQuery.error ||
    universeQuery.error ||
    queueQuery.error ||
    detailQuery.error ||
    optimizerQuery.error ||
    scheduleLinksQuery.error ||
    createProgrammeMutation.error ||
    updateProgrammeMutation.error ||
    updateItemMutation.error ||
    cancelItemMutation.error ||
    updateUniverseMutation.error ||
    optimizerMutation.error ||
    transitionMutation.error ||
    amendmentMutation.error ||
    itemMutation.error ||
    universeMutation.error;

  const openSchedule = (programmeId: string, itemId: string) => {
    if (!canManage) return;
    setScheduleTarget({ programmeId, itemId });
  };

  const selectedModel = normalizeAssuranceModel(selected?.assurance_model);
  const tabs: Array<{ id: WorkspaceTab; label: string }> = [
    { id: "requirements", label: "Programme" },
    { id: "universe", label: "Coverage areas" },
    { id: "readiness", label: "Approval" },
  ];
  const activeProgrammeItems = useMemo(
    () => (selected?.items || []).filter((item) => item.state !== "CANCELLED"),
    [selected?.items],
  );
  const linkedRequirementCount = (universeItemId: string) =>
    (selected?.items || []).filter((item) => item.universe_item_id === universeItemId).length;
  const unscheduledItems = (selected?.items || []).filter((item) => item.state === "PLANNED");
  const showAddAuditPrimary = Boolean(
    selected && canManage && programmeEditable(selected.status) && workspaceTab === "requirements",
  );
  const showNewProgrammePrimary = allowCreateProgramme && !showAddAuditPrimary;

  return (
    <div className="qms-audit-programme qms-audit-programme-flow" aria-label="Audit Programme workspace">
      <div className="qms-audit-programme-flow__context">
        <div className="qms-audit-programme-flow__context-main">
          <div className="qms-audit-programme-flow__context-title">
            <ClipboardCheck size={16} aria-hidden="true" />
            <div>
              <strong>Audit Programme</strong>
              <small>Plan audits for {year} · schedule dates in Calendar</small>
            </div>
          </div>
        </div>
        <div className="qms-audit-programme-flow__sticky-actions qms-audit-programme__header-actions">
          <div className="qms-audit-programme-flow__context-actions-secondary">
            {selected ? (
              <button
                type="button"
                className="is-secondary qms-audit-programme-flow__info-btn"
                onClick={() => setShowMethodologyInfo(true)}
                title="Methodology and assurance details"
              >
                <Info size={15} /> How this programme works
              </button>
            ) : null}
            <Link className="is-secondary qms-audit-programme-flow__planner-link" to={plannerHref}>
              <CalendarDays size={15} /> Open Calendar
            </Link>
            <label>
              <span>Year</span>
              <input
                type="number"
                min={2000}
                max={2200}
                value={year}
                onChange={(event) => setYear(Number(event.target.value) || currentYear)}
              />
            </label>
            <button
              type="button"
              className="is-secondary"
              onClick={() => {
                void programmesQuery.refetch();
                void universeQuery.refetch();
                void queueQuery.refetch();
                void optimizerQuery.refetch();
              }}
            >
              <RefreshCw size={15} /> Refresh
            </button>
          </div>
          {showAddAuditPrimary ? (
            <button type="button" className="is-primary" onClick={() => setShowRequirement(true)}>
              <Plus size={15} /> Add audit
            </button>
          ) : showNewProgrammePrimary ? (
            <button
              type="button"
              className="is-primary"
              onClick={() => {
                const nextKind = creatableKinds[0] || "INTERNAL";
                setProgrammeForm((current) => ({
                  ...current,
                  programme_kind: nextKind,
                  title: programmeKindTitle(nextKind, year),
                  period_start: `${year}-01-01`,
                  period_end: `${year}-12-31`,
                }));
                setShowCreate(true);
              }}
            >
              <Plus size={15} /> New programme
            </button>
          ) : null}
        </div>
      </div>

      <nav className="qms-audit-programme-flow__tabs" aria-label="Programme workspace sections">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={workspaceTab === tab.id ? "is-active" : ""}
            aria-current={workspaceTab === tab.id ? "page" : undefined}
            onClick={() => setWorkspaceTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {error ? (
        <div className="qms-audit-programme__error" role="alert">
          <AlertTriangle size={16} /> {error instanceof Error ? error.message : "Audit programme data could not be loaded."}
        </div>
      ) : null}

      {(workspaceTab === "requirements" || workspaceTab === "readiness") &&
      !programmesQuery.isLoading &&
      !visibleProgrammes.length ? (
        <div className="qms-audit-programme-flow__empty qms-audit-programme-flow__empty--portfolio" role="status">
          <div>
            <strong>No programme for {year}</strong>
            <p>Create a draft to plan internal, external, or third-party audits for this year.</p>
          </div>
          {allowCreateProgramme ? (
            <button
              type="button"
              className="is-primary"
              onClick={() => {
                const nextKind = creatableKinds[0] || "INTERNAL";
                setProgrammeForm((current) => ({
                  ...current,
                  programme_kind: nextKind,
                  title: programmeKindTitle(nextKind, year),
                  period_start: `${year}-01-01`,
                  period_end: `${year}-12-31`,
                }));
                setShowCreate(true);
              }}
            >
              <Plus size={15} /> Create programme
            </button>
          ) : canManage ? (
            <small>An active programme already exists for {year}. Amend it or close it before creating another.</small>
          ) : (
            <small>Audit manage permission is required to create a programme.</small>
          )}
        </div>
      ) : (
        <div className="qms-audit-programme__workspace qms-audit-programme-flow__workspace">
          <aside className="qms-audit-programme__portfolio">
            <header>
              <strong>Programmes · {year}</strong>
              <small>{visibleProgrammes.length} active</small>
            </header>
            {programmesQuery.isLoading ? (
              <p className="qms-audit-programme-flow__empty">Loading programmes…</p>
            ) : (
              visibleProgrammes.map((programme) => {
                const unscheduled = listedReadinessOf(programme)?.unscheduled_requirement_count;
                return (
                  <button
                    key={programme.id}
                    type="button"
                    className={`qms-audit-programme-flow__portfolio-card${programme.id === selectedProgrammeId ? " is-active" : ""}`}
                    onClick={() => {
                      setSelectedId(programme.id);
                    }}
                  >
                    <span className="qms-audit-programme-flow__portfolio-card-top">
                      <strong title={programmeDisplayLabel(programme)}>{programmeDisplayLabel(programme)}</strong>
                      <b className={`qms-chip qms-chip--${statusTone(programme.status)}`}>{human(programme.status)}</b>
                    </span>
                    <small className={unscheduled ? "is-warn" : ""}>
                      {programmePortfolioSummary(programme, unscheduled)}
                      {programme.revision_no > 1 ? ` · Rev ${programme.revision_no}` : ""}
                    </small>
                  </button>
                );
              })
            )}
          </aside>

          <section className="qms-audit-programme__detail">
            {workspaceTab === "universe" ? (
              <section
                className="qms-audit-programme-flow__coverage-panel"
                aria-labelledby="qms-audit-universe-heading"
              >
                <header className="qms-audit-programme-flow__coverage-header">
                  <div>
                    <h2 id="qms-audit-universe-heading">
                      <Library size={14} /> Coverage areas
                    </h2>
                    <p>
                      Departments, processes, and entities available for audit programmes.
                      {selected ? (
                        <>
                          {" "}
                          Showing linkage for <strong>{programmeDisplayLabel(selected)}</strong>.
                        </>
                      ) : (
                        <> Select a programme to see which areas are included.</>
                      )}
                    </p>
                  </div>
                  {canManage ? (
                    <button type="button" className="is-primary" onClick={() => setShowUniverseCreate(true)}>
                      <Plus size={14} /> Add area
                    </button>
                  ) : null}
                </header>
                {universeQuery.isLoading ? (
                  <p className="qms-audit-programme-flow__empty">Loading coverage areas…</p>
                ) : !(universeQuery.data?.items || []).length ? (
                  <div className="qms-audit-programme-flow__empty qms-audit-programme-flow__empty--portfolio">
                    <div>
                      <strong>No coverage areas yet</strong>
                      <p>Add departments, facilities, or other entities before planning audits.</p>
                    </div>
                    {canManage ? (
                      <button type="button" className="is-primary" onClick={() => setShowUniverseCreate(true)}>
                        <Plus size={14} /> Add first area
                      </button>
                    ) : null}
                  </div>
                ) : (
                  <div className="qms-audit-programme__table-wrap qms-audit-programme__table-wrap--dense">
                    <table>
                      <thead>
                        <tr>
                          <th>Area</th>
                          <th>Type</th>
                          <th>In programme</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(universeQuery.data?.items || []).map((item) => {
                          const linked = linkedRequirementCount(item.id);
                          return (
                            <tr key={item.id}>
                              <td>
                                <strong title={item.display_label}>{item.display_label}</strong>
                                {!item.active ? <small> · Inactive</small> : null}
                              </td>
                              <td>{human(item.entity_type)}</td>
                              <td>
                                {selectedProgrammeId ? (
                                  linked ? (
                                    <strong>{linked}</strong>
                                  ) : (
                                    <small className="is-muted">Not included</small>
                                  )
                                ) : (
                                  <small className="is-muted">—</small>
                                )}
                              </td>
                              <td className="qms-audit-programme-flow__row-actions">
                                <button type="button" className="is-secondary" onClick={() => openUniverseDrawer(item, false)}>
                                  View
                                </button>
                                {canManage ? (
                                  <button type="button" className="is-secondary" onClick={() => openUniverseDrawer(item, true)}>
                                    <Pencil size={12} /> Edit
                                  </button>
                                ) : null}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            ) : !selectedProgrammeId ? (
              <div className="qms-audit-programme-flow__empty qms-audit-programme-flow__empty--inline">
                <p>Select a programme revision.</p>
              </div>
            ) : detailQuery.isLoading ? (
              <p className="qms-audit-programme-flow__empty">Loading programme…</p>
            ) : !selected ? (
              <p className="qms-audit-programme-flow__empty">Programme not available.</p>
            ) : (
              <>
                {workspaceTab === "requirements" ? (
                  <header className="qms-audit-programme-flow__detail-toolbar">
                    <h2>Audits</h2>
                    <div className="qms-audit-programme-flow__detail-actions">
                      <button type="button" className="is-secondary" onClick={() => setShowProgrammeDetail(true)}>
                        Programme details
                      </button>
                      {canManage && programmeEditable(selected.status) ? (
                        <button type="button" className="is-secondary" onClick={() => openProgrammeEdit(selected)}>
                          <Pencil size={14} /> Edit programme
                        </button>
                      ) : null}
                    </div>
                  </header>
                ) : workspaceTab === "readiness" ? (
                  <header className="qms-audit-programme-flow__detail-toolbar">
                    <h2>Approval</h2>
                    <div className="qms-audit-programme-flow__detail-actions">
                      <button type="button" className="is-secondary" onClick={() => setShowProgrammeDetail(true)}>
                        Programme details
                      </button>
                    </div>
                  </header>
                ) : null}

                {workspaceTab === "requirements" ? (
                  <>
                    <section className="qms-audit-programme__requirements qms-audit-programme-flow__coverage qms-audit-programme-flow__programme-main">
                      {!activeProgrammeItems.length ? (
                        <div className="qms-audit-programme-flow__empty qms-audit-programme-flow__empty--portfolio">
                          <div>
                            <strong>No audits in this programme yet</strong>
                            <p>Add audits for departments, processes, or suppliers you plan to review this year.</p>
                          </div>
                          {canManage && programmeEditable(selected.status) ? (
                            <button type="button" className="is-primary" onClick={() => setShowRequirement(true)}>
                              <Plus size={14} /> Add first audit
                            </button>
                          ) : null}
                        </div>
                      ) : (
                        <DataTableShell>
                          <div className="qms-audit-programme__table-wrap qms-audit-programme__table-wrap--dense">
                            <table>
                              <thead>
                                <tr>
                                  <th>Audit</th>
                                  <th>Area</th>
                                  <th>Frequency</th>
                                  <th>Status</th>
                                  <th>Target window</th>
                                  <th>Actions</th>
                                </tr>
                              </thead>
                              <tbody>
                                {activeProgrammeItems.map((item) => {
                                  const link = linksByItem.get(item.id);
                                  const isUnscheduled = item.state === "PLANNED";
                                  return (
                                    <tr key={item.id} className={isUnscheduled ? "is-unscheduled" : ""}>
                                      <td>
                                        <strong title={item.title}>{item.title}</strong>
                                        <small>{human(item.audit_type)}</small>
                                      </td>
                                      <td>
                                        {item.auditable_entity?.display_label || "Unlinked"}
                                        {item.mandatory_surveillance ? (
                                          <small> · Mandatory</small>
                                        ) : null}
                                      </td>
                                      <td>{human(item.recurrence)}</td>
                                      <td>
                                        <span className={`qms-chip qms-chip--${statusTone(item.state)}`}>{human(item.state)}</span>
                                        {link?.next_due_date ? (
                                          <small>Due {dateLabel(link.next_due_date)}</small>
                                        ) : isUnscheduled ? (
                                          <small className="is-muted">Not on calendar</small>
                                        ) : null}
                                      </td>
                                      <td>
                                        {dateLabel(item.target_start)}
                                        <small>to {dateLabel(item.target_end)}</small>
                                      </td>
                                      <td className="qms-audit-programme-flow__row-actions">
                                        <button type="button" className="is-secondary" onClick={() => openRequirementDrawer(item, false)}>
                                          View
                                        </button>
                                        {canManage && programmeEditable(selected.status) ? (
                                          <>
                                            <button type="button" className="is-secondary" onClick={() => openRequirementDrawer(item, true)}>
                                              <Pencil size={14} /> Edit
                                            </button>
                                            <button
                                              type="button"
                                              className="is-secondary is-danger"
                                              onClick={() => {
                                                setCancelItemTarget(item);
                                                setCancelItemReason("");
                                              }}
                                              title="Remove audit from programme"
                                            >
                                              <Trash2 size={14} /> Remove
                                            </button>
                                          </>
                                        ) : null}
                                        {isUnscheduled ? (
                                          canManage ? (
                                            <button
                                              type="button"
                                              className="is-schedule"
                                              onClick={() => openSchedule(selected.id, item.id)}
                                            >
                                              Schedule <CalendarClock size={14} />
                                            </button>
                                          ) : null
                                        ) : (
                                          <Link className="is-secondary" to={plannerHref}>
                                            Calendar <CalendarDays size={14} />
                                          </Link>
                                        )}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </DataTableShell>
                      )}
                    </section>

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
                            <small>{queue.length} approved audit{queue.length === 1 ? "" : "s"} waiting for a calendar date.</small>
                          </div>
                          <Link to={plannerHref}>Open Calendar <ArrowRight size={14} /></Link>
                        </header>
                        <div>
                          {queue.slice(0, 6).map((item) =>
                            SCHEDULABLE_RECURRENCES.has(item.recurrence) && canManage ? (
                              <button
                                key={item.programme_item_id}
                                type="button"
                                onClick={() => openSchedule(item.programme_id, item.programme_item_id)}
                                title={item.title}
                              >
                                <span>
                                  <strong title={item.title}>{item.title}</strong>
                                  <small>
                                    {dateLabel(item.target_start)} → {dateLabel(item.target_end)} · {human(item.recurrence)}
                                  </small>
                                </span>
                                <CalendarClock size={16} />
                              </button>
                            ) : (
                              <span key={item.programme_item_id} title={item.title}>
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
                    <section
                      className={`qms-audit-programme-flow__readiness ${readiness.ready_for_approval ? "is-ready" : "is-blocked"}`}
                      aria-label="Programme approval status"
                    >
                      <div>
                        {readiness.ready_for_approval ? <CheckCircle2 size={18} /> : <TriangleAlert size={18} />}
                        <span>
                          <strong>
                            {readiness.ready_for_approval
                              ? "Ready to submit for approval"
                              : "Not ready for approval yet"}
                          </strong>
                          <small>
                            {readiness.ready_for_approval
                              ? "All required setup is complete for this revision."
                              : "Complete the items below before submitting."}
                          </small>
                        </span>
                      </div>
                      {!readiness.ready_for_approval && readiness.blockers.length ? (
                        <ul>
                          {readiness.blockers.slice(0, 8).map((blocker, index) => (
                            <li key={`${blocker.code}-${index}`}>{blocker.message}</li>
                          ))}
                        </ul>
                      ) : null}
                    </section>

                    <section className="qms-audit-programme-flow__readiness-stats qms-audit-programme-flow__readiness-stats--two" aria-label="Programme summary">
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
                        <strong>{readiness.unscheduled_requirement_count}</strong>
                        <small>
                          {unscheduledItems.length
                            ? "Assign calendar dates after approval"
                            : "All audits have schedule links or are complete"}
                        </small>
                      </article>
                    </section>

                    {transitionTargets(selected.status).length ||
                    (selected.status !== "DRAFT" && selected.status !== "SUPERSEDED" && canManage) ? (
                      <section className="qms-audit-programme-flow__approval-panel" aria-label="Approval actions">
                        <p>
                          {selected.status === "DRAFT"
                            ? "Submit this draft for review when setup is complete."
                            : "Record your decision or create an amendment for later changes."}
                        </p>
                        <div className="qms-audit-programme-flow__approval-actions">
                          <input
                            aria-label="Reason for this action"
                            value={actionReason}
                            onChange={(event) => setActionReason(event.target.value)}
                            placeholder="Reason for this approval action"
                          />
                          {transitionTargets(selected.status).map((target) => {
                            const isForward = forwardTransition(selected.status, target);
                            const label =
                              target === "UNDER_REVIEW" ? "Submit for review" : human(target);
                            return (
                              <button
                                key={target}
                                type="button"
                                className={isForward ? "is-primary" : "is-secondary"}
                                disabled={
                                  !canManage ||
                                  actionReason.trim().length < 3 ||
                                  transitionMutation.isPending ||
                                  (target === "APPROVED" && !readiness.ready_for_approval)
                                }
                                onClick={() => transitionMutation.mutate(target)}
                              >
                                {label} {isForward ? <ArrowRight size={14} /> : null}
                              </button>
                            );
                          })}
                          {selected.status !== "DRAFT" && selected.status !== "SUPERSEDED" && canManage ? (
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
                      </section>
                    ) : null}

                    <details className="qms-audit-programme-flow__history">
                      <summary>
                        Programme history <small>{selected.events?.length || 0} events</small>
                      </summary>
                      <div>
                        {[...(selected.events || [])].reverse().map((event) => (
                          <article key={event.id}>
                            <span>
                              <strong>{human(event.event_type)}</strong>
                              <small>{new Date(event.created_at).toLocaleString()}</small>
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

      <Drawer title="Create programme" isOpen={showCreate} onClose={() => setShowCreate(false)} side="right" panelClassName="qms-audit-programme-drawer qms-audit-programme-flow__create-drawer">
        <form
          className="qms-audit-programme__form qms-audit-programme-flow__create"
          onSubmit={(event) => {
            event.preventDefault();
            createProgrammeMutation.mutate();
          }}
        >
          <div className="qms-audit-programme-drawer__body">
            <p className="qms-audit-programme-flow__drawer-note">
              One programme per type for {year}. Period defaults to the full calendar year.
            </p>
            <label className="is-wide">
              <span>Programme type</span>
              <select
                required
                value={programmeForm.programme_kind}
                onChange={(event) => {
                  const programme_kind = event.target.value as ProgrammeKind;
                  setProgrammeForm((current) => ({
                    ...current,
                    programme_kind,
                    title: programmeKindTitle(programme_kind, year),
                  }));
                }}
              >
                {PROGRAMME_KINDS.filter((entry) => creatableKinds.includes(entry.id)).map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.label}
                  </option>
                ))}
              </select>
            </label>
            <p className="qms-audit-programme-flow__drawer-note is-compact">
              Title: <strong>{programmeForm.title}</strong> · {dateLabel(programmeForm.period_start)} →{" "}
              {dateLabel(programmeForm.period_end)}
            </p>
            <label className="is-wide">
              <span>Programme objectives · one per line</span>
              <textarea
                rows={3}
                value={programmeForm.objectives}
                onChange={(event) => setProgrammeForm((current) => ({ ...current, objectives: event.target.value }))}
              />
            </label>
            <label className="is-wide">
              <span>Compliance baseline · one governing reference per line</span>
              <textarea
                rows={4}
                value={programmeForm.regulatory_basis}
                onChange={(event) => setProgrammeForm((current) => ({ ...current, regulatory_basis: event.target.value }))}
                placeholder="KCAR / approval condition / MPM / QMSM / IOSA / ISO / customer or contractual requirement"
              />
            </label>
          </div>
          <div className="qms-audit-programme-drawer__footer">
            <button type="button" className="is-secondary" onClick={() => setShowCreate(false)}>
              Cancel
            </button>
            <button type="submit" className="is-primary" disabled={createProgrammeMutation.isPending}>
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
              <span>Auditable entity</span>
              <select
                required
                value={itemForm.universe_item_id}
                onChange={(event) => setItemForm((current) => ({ ...current, universe_item_id: event.target.value }))}
              >
                <option value="">Select entity</option>
                {(universeQuery.data?.items || [])
                  .filter((item) => item.active)
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.display_label} · {human(item.entity_type)}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              <span>Audit subject / coverage type</span>
              <select
                value={itemForm.audit_type}
                onChange={(event) => setItemForm((current) => ({ ...current, audit_type: event.target.value }))}
              >
                {AUDIT_SUBJECTS.map((value) => (
                  <option key={value} value={value}>
                    {human(value)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Cadence</span>
              <select
                value={itemForm.recurrence}
                onChange={(event) => setItemForm((current) => ({ ...current, recurrence: event.target.value }))}
              >
                {RECURRENCES.map((value) => (
                  <option key={value} value={value}>
                    {human(value)}
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
                onChange={(event) => setItemForm((current) => ({ ...current, title: event.target.value }))}
              />
            </label>
            <label className="is-wide">
              <span>Purpose / reason for this audit</span>
              <textarea
                rows={2}
                value={itemForm.purpose}
                onChange={(event) => setItemForm((current) => ({ ...current, purpose: event.target.value }))}
              />
            </label>
            <label className="is-wide">
              <span>Scope</span>
              <textarea
                required
                rows={3}
                value={itemForm.scope}
                onChange={(event) => setItemForm((current) => ({ ...current, scope: event.target.value }))}
              />
            </label>
            <label className="is-wide">
              <span>Audit criteria · one reference per line</span>
              <textarea
                required
                rows={3}
                value={itemForm.criteria}
                onChange={(event) => setItemForm((current) => ({ ...current, criteria: event.target.value }))}
              />
            </label>
            <label>
              <span>Target window start</span>
              <input
                required
                type="date"
                value={itemForm.target_start}
                onChange={(event) => setItemForm((current) => ({ ...current, target_start: event.target.value }))}
              />
            </label>
            <label>
              <span>Target window end</span>
              <input
                required
                type="date"
                value={itemForm.target_end}
                onChange={(event) => setItemForm((current) => ({ ...current, target_end: event.target.value }))}
              />
            </label>
            <label className="is-checkbox">
              <input
                type="checkbox"
                checked={itemForm.mandatory_surveillance}
                onChange={(event) => setItemForm((current) => ({ ...current, mandatory_surveillance: event.target.checked }))}
              />
              <span>Mandatory / minimum surveillance</span>
            </label>
          </div>
          <div className="qms-audit-programme-drawer__footer">
            <button type="button" className="is-secondary" onClick={() => setShowRequirement(false)}>
              Cancel
            </button>
            <button type="submit" className="is-primary" disabled={itemMutation.isPending}>
              Add to programme
            </button>
          </div>
        </form>
      </Drawer>

      <Drawer
        title="Add coverage area"
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
              Register a department, facility, or other entity for use across programmes.
            </p>
          <label>
            <span>Entity type</span>
            <select
              value={universeForm.entity_type}
              onChange={(event) =>
                setUniverseForm((current) => ({ ...current, entity_type: event.target.value as AuditUniverseEntityType }))
              }
            >
              {UNIVERSE_TYPES.map((value) => (
                <option key={value} value={value}>
                  {human(value)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Display label</span>
            <input
              required
              value={universeForm.display_label}
              onChange={(event) => setUniverseForm((current) => ({ ...current, display_label: event.target.value }))}
            />
          </label>
          <label>
            <span>Risk level</span>
            <select
              value={universeForm.risk_classification}
              onChange={(event) =>
                setUniverseForm((current) => ({ ...current, risk_classification: event.target.value as AuditRiskLevel }))
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
                  regulatory_criticality: event.target.value as AuditRiskLevel,
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
          <details className="qms-audit-programme-flow__drawer-advanced">
            <summary>Source linkage & surveillance settings</summary>
            <div className="qms-audit-programme-flow__drawer-advanced-body">
          <label>
            <span>Authoritative source module</span>
            <input
              value={universeForm.source_owner_module}
              placeholder="AUDIT_PROGRAMME"
              onChange={(event) => setUniverseForm((current) => ({ ...current, source_owner_module: event.target.value }))}
            />
          </label>
          <label>
            <span>Source record type</span>
            <input
              value={universeForm.source_type}
              onChange={(event) => setUniverseForm((current) => ({ ...current, source_type: event.target.value }))}
            />
          </label>
          <label>
            <span>Source record ID</span>
            <input
              value={universeForm.source_id}
              placeholder="Auto-generated from label if left blank"
              onChange={(event) => setUniverseForm((current) => ({ ...current, source_id: event.target.value }))}
            />
          </label>
          <label>
            <span>Source route</span>
            <input
              value={universeForm.source_route}
              onChange={(event) => setUniverseForm((current) => ({ ...current, source_route: event.target.value }))}
            />
          </label>
          <label>
            <span>Maximum surveillance interval (days)</span>
            <input
              type="number"
              min={1}
              value={universeForm.surveillance_interval_days}
              onChange={(event) =>
                setUniverseForm((current) => ({ ...current, surveillance_interval_days: event.target.value }))
              }
            />
          </label>
          <label className="is-checkbox">
            <input
              type="checkbox"
              checked={universeForm.mandatory_surveillance}
              onChange={(event) =>
                setUniverseForm((current) => ({ ...current, mandatory_surveillance: event.target.checked }))
              }
            />
            <span>Mandatory surveillance floor</span>
          </label>
            </div>
          </details>
          <label className="is-wide">
            <span>Notes</span>
            <textarea
              rows={2}
              value={universeForm.notes}
              onChange={(event) => setUniverseForm((current) => ({ ...current, notes: event.target.value }))}
            />
            </label>
          </div>
          <div className="qms-audit-programme-drawer__footer">
            <button type="button" className="is-secondary" onClick={() => setShowUniverseCreate(false)}>
              Cancel
            </button>
            <button type="submit" className="is-primary" disabled={universeMutation.isPending}>
              Add area
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
              Optional detail for quality managers. Day-to-day work is adding audits and scheduling them in Calendar.
            </p>
            <section className="qms-audit-programme-flow__basis qms-audit-programme-flow__basis--compact" aria-label="Assurance methodology">
              <div className="is-risk">
                <span>Methodology</span>
                <strong>{methodologyLabel(selectedModel)}{selected.continuous_monitoring_enabled ? " · Continuous monitoring" : ""}</strong>
                <div className="qms-audit-programme-flow__method-pillars" aria-label="Programme strategy">
                  {METHODOLOGY_PILLARS.map((pillar) => {
                    const weight =
                      pillar.id === "COMPLIANCE"
                        ? optimizer?.weights?.compliance
                        : pillar.id === "RISK"
                          ? optimizer?.weights?.risk
                          : pillar.id === "PERFORMANCE"
                            ? optimizer?.weights?.performance
                            : null;
                    const active = selectedModel === pillar.id;
                    return (
                      <span key={pillar.id} className={active ? "is-active" : ""}>
                        <b>{pillar.label}</b>
                        <small>
                          {pillar.id === "HYBRID"
                            ? active
                              ? "Active programme strategy"
                              : pillar.hint
                            : typeof weight === "number"
                              ? `${Math.round(weight * 100)}%`
                              : pillar.hint}
                        </small>
                      </span>
                    );
                  })}
                </div>
              </div>
              <dl>
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
              className="qms-audit-programme-flow__queue qms-audit-programme-flow__queue--compact"
              aria-label="Hybrid assurance optimizer"
            >
              <header>
                <div>
                  <strong>
                    <BrainCircuit size={15} /> Assurance optimizer
                  </strong>
                  <small>Compliance, risk, and performance scoring used to recommend coverage.</small>
                </div>
                {canManage ? (
                  <button
                    type="button"
                    className="is-secondary"
                    disabled={optimizerMutation.isPending}
                    onClick={() => optimizerMutation.mutate()}
                  >
                    <RefreshCw size={14} /> Recalculate
                  </button>
                ) : null}
              </header>
              {optimizerQuery.isLoading ? (
                <p className="qms-audit-programme-flow__empty">Calculating surveillance priorities…</p>
              ) : optimizer ? (
                <>
                  <div className="qms-audit-programme-flow__optimizer-summary">
                    <span>
                      <small>Compliance</small>
                      <strong>{Math.round((optimizer.weights?.compliance || 0) * 100)}%</strong>
                    </span>
                    <span>
                      <small>Risk</small>
                      <strong>{Math.round((optimizer.weights?.risk || 0) * 100)}%</strong>
                    </span>
                    <span>
                      <small>Performance</small>
                      <strong>{Math.round((optimizer.weights?.performance || 0) * 100)}%</strong>
                    </span>
                    <span>
                      <small>Coverage gaps</small>
                      <strong>{optimizer.summary?.coverage_gaps || 0}</strong>
                    </span>
                  </div>
                  {optimizer.governance?.message ? (
                    <p className="qms-audit-programme-flow__optimizer-note">
                      <ShieldCheck size={14} /> {optimizer.governance.message}
                    </p>
                  ) : null}
                  <div className="qms-audit-programme-flow__optimizer-list">
                    {(optimizer.recommendations || [])
                      .filter((entry) => entry.recommended_in_current_programme || entry.in_programme)
                      .slice(0, 12)
                      .map((entry) => (
                        <article key={entry.universe_item_id}>
                          <span>
                            <b>{entry.priority_score}</b>
                            <small>{human(entry.priority_band)}</small>
                          </span>
                          <div>
                            <strong title={entry.auditable_entity}>{entry.auditable_entity}</strong>
                            <small>
                              Compliance {entry.components.compliance} · Risk {entry.components.risk} · Performance{" "}
                              {entry.components.performance}
                            </small>
                            <small>
                              {entry.signals.repeat_findings
                                ? `${entry.signals.repeat_findings} repeat finding signal(s) · `
                                : ""}
                              {entry.signals.open_findings ? `${entry.signals.open_findings} open finding(s) · ` : ""}
                              recommended every {entry.recommended_interval_days} days
                            </small>
                          </div>
                          <span>
                            {entry.in_programme ? (
                              <b className="qms-chip qms-chip--good">Covered</b>
                            ) : entry.requires_amendment ? (
                              <b className="qms-chip qms-chip--warn">Amend</b>
                            ) : (
                              <b className="qms-chip">Recommended</b>
                            )}
                            <small>Due {dateLabel(entry.next_recommended_due)}</small>
                          </span>
                        </article>
                      ))}
                  </div>
                </>
              ) : (
                <p className="qms-audit-programme-flow__empty">No optimizer result is available.</p>
              )}
            </section>
              </div>
            </div>
            <div className="qms-audit-programme-drawer__footer">
              <button type="button" className="is-secondary" onClick={() => setShowMethodologyInfo(false)}>
                Close
              </button>
            </div>
          </>
        ) : null}
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
              <p className="qms-audit-programme-flow__drawer-note">
                Removes <strong>{cancelItemTarget.title}</strong> from this programme revision. A reason is required.
              </p>
              <label className="is-wide">
                <span>Reason for removal</span>
                <input
                  required
                  minLength={3}
                  value={cancelItemReason}
                  onChange={(event) => setCancelItemReason(event.target.value)}
                  placeholder="Why this audit is no longer required"
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
                Keep audit
              </button>
              <button
                type="submit"
                className="is-danger"
                disabled={cancelItemMutation.isPending || cancelItemReason.trim().length < 3}
              >
                <Trash2 size={14} /> Remove audit
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
                  <p className="qms-audit-programme-flow__drawer-note">{programmeStatusHint(selected.status)}</p>
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
                      {dateLabel(selected.period_start)} → {dateLabel(selected.period_end)}
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
              <button type="button" className="is-secondary" onClick={() => setShowProgrammeDetail(false)}>
                Close
              </button>
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
                onChange={(event) => setEditProgrammeForm((current) => ({ ...current, title: event.target.value }))}
              />
            </label>
            <label>
              <span>Period start</span>
              <input
                type="date"
                required
                value={editProgrammeForm.period_start}
                onChange={(event) => setEditProgrammeForm((current) => ({ ...current, period_start: event.target.value }))}
              />
            </label>
            <label>
              <span>Period end</span>
              <input
                type="date"
                required
                value={editProgrammeForm.period_end}
                onChange={(event) => setEditProgrammeForm((current) => ({ ...current, period_end: event.target.value }))}
              />
            </label>
            <label className="is-wide">
              <span>Objectives · one per line</span>
              <textarea
                rows={4}
                value={editProgrammeForm.objectives}
                onChange={(event) => setEditProgrammeForm((current) => ({ ...current, objectives: event.target.value }))}
              />
            </label>
            <label className="is-wide">
              <span>Regulatory basis · one per line</span>
              <textarea
                rows={3}
                value={editProgrammeForm.regulatory_basis}
                onChange={(event) => setEditProgrammeForm((current) => ({ ...current, regulatory_basis: event.target.value }))}
              />
            </label>
            <label className="is-wide">
              <span>Change reason</span>
              <input
                required
                minLength={3}
                value={editReason}
                onChange={(event) => setEditReason(event.target.value)}
                placeholder="Why this programme revision is being updated"
              />
            </label>
          </div>
          <div className="qms-audit-programme-drawer__footer">
            <button type="button" className="is-secondary" onClick={() => setShowProgrammeEdit(false)}>
              Cancel
            </button>
            <button type="submit" className="is-primary" disabled={updateProgrammeMutation.isPending || editReason.trim().length < 3}>
              Save programme
            </button>
          </div>
        </form>
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
                    <dd>{requirementFocus.auditable_entity?.display_label || "—"}</dd>
                  </div>
                  <div>
                    <dt>Window</dt>
                    <dd>
                      {dateLabel(requirementFocus.target_start)} → {dateLabel(requirementFocus.target_end)}
                    </dd>
                  </div>
                  <div>
                    <dt>Recurrence</dt>
                    <dd>{human(requirementFocus.recurrence)}</dd>
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
                    <dd>{linksByItem.get(requirementFocus.id)?.schedule_id ? "On calendar" : "Not scheduled"}</dd>
                  </div>
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
              {canManage && selected && programmeEditable(selected.status) ? (
                <button type="button" className="is-primary" onClick={() => openRequirementDrawer(requirementFocus, true)}>
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
                  onChange={(event) => setEditItemForm((current) => ({ ...current, title: event.target.value }))}
                />
              </label>
              <label className="is-wide">
                <span>Purpose</span>
                <textarea
                  rows={2}
                  value={editItemForm.purpose}
                  onChange={(event) => setEditItemForm((current) => ({ ...current, purpose: event.target.value }))}
                />
              </label>
              <label className="is-wide">
                <span>Scope</span>
                <textarea
                  required
                  minLength={3}
                  rows={3}
                  value={editItemForm.scope}
                  onChange={(event) => setEditItemForm((current) => ({ ...current, scope: event.target.value }))}
                />
              </label>
              <label className="is-wide">
                <span>Criteria · one per line</span>
                <textarea
                  rows={3}
                  value={editItemForm.criteria}
                  onChange={(event) => setEditItemForm((current) => ({ ...current, criteria: event.target.value }))}
                />
              </label>
              <label>
                <span>Recurrence</span>
                <select
                  value={editItemForm.recurrence}
                  onChange={(event) => setEditItemForm((current) => ({ ...current, recurrence: event.target.value }))}
                >
                  {RECURRENCES.map((value) => (
                    <option key={value} value={value}>
                      {human(value)}
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
                    setEditItemForm((current) => ({ ...current, mandatory_surveillance: event.target.checked }))
                  }
                />
              </label>
              <label>
                <span>Target start</span>
                <input
                  type="date"
                  value={editItemForm.target_start}
                  onChange={(event) => setEditItemForm((current) => ({ ...current, target_start: event.target.value }))}
                />
              </label>
              <label>
                <span>Target end</span>
                <input
                  type="date"
                  value={editItemForm.target_end}
                  onChange={(event) => setEditItemForm((current) => ({ ...current, target_end: event.target.value }))}
                />
              </label>
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
              <button type="submit" className="is-primary" disabled={updateItemMutation.isPending || editReason.trim().length < 3}>
                Save
              </button>
            </div>
          </form>
        ) : null}
      </Drawer>

      <Drawer
        title={universeEditMode ? "Edit coverage area" : "Coverage area details"}
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
                    <dt>Source module</dt>
                    <dd>{human(universeFocus.source_owner_module.replace(/_/g, " "))}</dd>
                  </div>
                  <div>
                    <dt>Source type</dt>
                    <dd>{human(universeFocus.source_type)}</dd>
                  </div>
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
                    <dd>{universeFocus.surveillance_interval_days ?? "—"} days</dd>
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
                        <Link to={universeFocus.source_route}>Open source record</Link>
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
                <button type="button" className="is-primary" onClick={() => openUniverseDrawer(universeFocus, true)}>
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
                Source identity is read-only. You can update label, route, risk, and surveillance settings.
              </p>
              <label className="is-wide">
                <span>Display label</span>
                <input
                  required
                  minLength={2}
                  value={editUniverseForm.display_label}
                  onChange={(event) => setEditUniverseForm((current) => ({ ...current, display_label: event.target.value }))}
                />
              </label>
              <label className="is-wide">
                <span>Source route</span>
                <input
                  value={editUniverseForm.source_route}
                  onChange={(event) => setEditUniverseForm((current) => ({ ...current, source_route: event.target.value }))}
                />
              </label>
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
                      regulatory_criticality: event.target.value as AuditRiskLevel,
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
                <span>Surveillance interval (days)</span>
                <input
                  type="number"
                  min={1}
                  value={editUniverseForm.surveillance_interval_days}
                  onChange={(event) =>
                    setEditUniverseForm((current) => ({ ...current, surveillance_interval_days: event.target.value }))
                  }
                />
              </label>
              <label>
                <span>Mandatory surveillance</span>
                <input
                  type="checkbox"
                  checked={editUniverseForm.mandatory_surveillance}
                  onChange={(event) =>
                    setEditUniverseForm((current) => ({ ...current, mandatory_surveillance: event.target.checked }))
                  }
                />
              </label>
              <label>
                <span>Active</span>
                <input
                  type="checkbox"
                  checked={editUniverseForm.active}
                  onChange={(event) => setEditUniverseForm((current) => ({ ...current, active: event.target.checked }))}
                />
              </label>
              <label className="is-wide">
                <span>Notes</span>
                <textarea
                  rows={3}
                  value={editUniverseForm.notes}
                  onChange={(event) => setEditUniverseForm((current) => ({ ...current, notes: event.target.value }))}
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
              <button type="submit" className="is-primary" disabled={updateUniverseMutation.isPending}>
                Save
              </button>
            </div>
          </form>
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
    </div>
  );
};

export default QmsAuditProgrammePageV2;
