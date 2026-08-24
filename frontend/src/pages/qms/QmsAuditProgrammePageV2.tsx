import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CalendarClock,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  Gauge,
  Library,
  Pencil,
  Plus,
  RefreshCw,
  ShieldCheck,
  Target,
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
  listAuditProgrammeScheduleLinks,
  listAuditProgrammeSchedulingQueue,
  listAuditProgrammes,
  listAuditUniverse,
  rebuildAuditProgrammeOptimizer,
  transitionAuditProgramme,
  updateAuditProgramme,
  updateAuditProgrammeItem,
  updateAuditUniverseItem,
  type AuditAssuranceModel,
  type AuditProgramme,
  type AuditProgrammeItem,
  type AuditProgrammeList,
  type AuditProgrammeOptimizer,
  type AuditProgrammeStatus,
  type AuditRiskLevel,
  type AuditUniverseEntityType,
  type AuditUniverseItem,
} from "../../services/qmsAuditProgramme";
import QmsAuditProgrammeSchedulePanel from "./QmsAuditProgrammeSchedulePanel";
import "../../styles/qms-audit-programme.css";
import "../../styles/qms-audit-programme-workflow.css";

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
const METHODOLOGY_PILLARS: Array<{ id: "COMPLIANCE" | "RISK" | "PERFORMANCE"; label: string; hint: string }> = [
  { id: "COMPLIANCE", label: "Compliance", hint: "Regulatory / contractual floor" },
  { id: "RISK", label: "Risk", hint: "Inherent & residual exposure" },
  { id: "PERFORMANCE", label: "Performance", hint: "Findings, trends, KPIs" },
];

type WorkspaceTab = "portfolio" | "requirements" | "universe" | "readiness";

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
  return human(normalizeAssuranceModel(model));
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

function readinessOf(programme?: AuditProgramme, optimizer?: AuditProgrammeOptimizer) {
  const items = programme?.items || [];
  const server = programme?.readiness;
  const blockers = server ? [...server.blockers] : ([] as Array<{ code: string; message: string }>);
  if (!server) {
    if (!items.length) blockers.push({ code: "NO_REQUIREMENTS", message: "No governed audit coverage is defined yet." });
    if (!programme?.regulatory_basis?.length) blockers.push({ code: "NO_COMPLIANCE_BASIS", message: "Add the applicable compliance baseline before approval." });
    items.forEach((item) => {
      if (!item.target_start || !item.target_end) blockers.push({ code: "MISSING_TARGET_WINDOW", message: `${item.title}: set a target window.` });
      if (!item.criteria?.length) blockers.push({ code: "MISSING_CRITERIA", message: `${item.title}: add audit criteria.` });
    });
  }
  const mandatoryGaps = optimizer?.summary?.mandatory_coverage_gaps || 0;
  if (mandatoryGaps && !blockers.some((entry) => entry.code === "MANDATORY_COVERAGE_GAP")) {
    blockers.push({
      code: "MANDATORY_COVERAGE_GAP",
      message: `${mandatoryGaps} mandatory surveillance requirement(s) due this period are not covered.`,
    });
  }
  return {
    ready_for_approval: blockers.length === 0,
    blockers,
    requirement_count: server?.requirement_count ?? items.length,
    mandatory_requirement_count: server?.mandatory_requirement_count ?? items.filter((item) => item.mandatory_surveillance).length,
    mandatory_unscheduled_count:
      server?.mandatory_unscheduled_count ?? items.filter((item) => item.mandatory_surveillance && item.state === "PLANNED").length,
    high_risk_requirement_count:
      server?.high_risk_requirement_count ??
      items.filter((item) => ["HIGH", "CRITICAL"].includes(item.auditable_entity?.risk_classification || "")).length,
    unscheduled_requirement_count: server?.unscheduled_requirement_count ?? items.filter((item) => item.state === "PLANNED").length,
  };
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
  const [showProgrammeEdit, setShowProgrammeEdit] = useState(false);
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
  const selectedProgrammeId = selectedId || programmes[0]?.id || null;
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
    title: `${currentYear} Quality Audit Programme`,
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
    mutationFn: () =>
      createAuditUniverseItem(amoCode, {
        entity_type: universeForm.entity_type,
        display_label: universeForm.display_label.trim(),
        source_owner_module: universeForm.source_owner_module.trim(),
        source_type: universeForm.source_type.trim(),
        source_id: universeForm.source_id.trim(),
        source_route: universeForm.source_route.trim() || undefined,
        risk_classification: universeForm.risk_classification,
        regulatory_criticality: universeForm.regulatory_criticality,
        surveillance_interval_days: universeForm.surveillance_interval_days
          ? Number(universeForm.surveillance_interval_days)
          : undefined,
        mandatory_surveillance: universeForm.mandatory_surveillance,
        notes: universeForm.notes.trim() || undefined,
      }),
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
  const scheduledCount = selected?.metrics?.scheduled_audit_count ?? (selected?.items || []).filter((item) => item.state === "SCHEDULED").length;
  const coverageGaps = optimizer?.summary?.coverage_gaps ?? 0;
  const tabs: Array<{ id: WorkspaceTab; label: string; hint: string }> = [
    { id: "portfolio", label: "Portfolio", hint: "Revisions" },
    { id: "requirements", label: "Requirements", hint: "Coverage" },
    { id: "universe", label: "Universe", hint: "Entities" },
    { id: "readiness", label: "Readiness", hint: "Approve" },
  ];
  const linkedRequirementCount = (universeItemId: string) =>
    (selected?.items || []).filter((item) => item.universe_item_id === universeItemId).length;
  const unscheduledItems = (selected?.items || []).filter((item) => item.state === "PLANNED");
  const missingMappingItems = (selected?.items || []).filter((item) => !item.universe_item_id || !item.auditable_entity);
  const coverageGapCount = optimizer?.summary?.coverage_gaps ?? selected?.readiness?.mandatory_coverage_gap_count ?? null;

  return (
    <div className="qms-audit-programme qms-audit-programme-flow" aria-label="Audit Programme workspace">
      <div className="qms-audit-programme-flow__context">
        <div className="qms-audit-programme-flow__context-main">
          <div className="qms-audit-programme-flow__context-title">
            <ClipboardCheck size={16} aria-hidden="true" />
            <div>
              <strong title={selected?.title || `Audit Programme · ${year}`}>{selected?.title || `Audit Programme · ${year}`}</strong>
              <small title={selected ? `${selected.programme_ref}` : undefined}>
                Coverage authority · Planner V2 owns dates
                {selected ? ` · ${selected.programme_ref}` : ""}
              </small>
            </div>
          </div>
          <div className="qms-audit-programme-flow__chips" aria-label="Active programme signals">
            {selected ? (
              <>
                <span className={`qms-chip qms-chip--${statusTone(selected.status)}`}>{human(selected.status)}</span>
                <span className="qms-chip qms-chip--method" title={selectedModel === "HYBRID" ? "Hybrid · Always on" : methodologyLabel(selectedModel)}>
                  {selectedModel === "HYBRID" ? "Hybrid · Always on" : methodologyLabel(selectedModel)}
                </span>
                <span className="qms-chip">
                  {dateLabel(selected.period_start)} → {dateLabel(selected.period_end)}
                </span>
                <span className="qms-chip">Rev {selected.revision_no}</span>
              </>
            ) : (
              <span className="qms-chip qms-chip--muted">No programme selected</span>
            )}
            <span className="qms-chip">{readiness.requirement_count} requirements</span>
            <span className={`qms-chip${readiness.unscheduled_requirement_count ? " qms-chip--warn" : ""}`}>
              {readiness.unscheduled_requirement_count} unscheduled
            </span>
            <span className="qms-chip">{scheduledCount} planned on calendar</span>
            {coverageGaps ? <span className="qms-chip qms-chip--danger">{coverageGaps} coverage gaps</span> : null}
          </div>
        </div>
        <div className="qms-audit-programme-flow__sticky-actions qms-audit-programme__header-actions">
          <Link className="qms-audit-programme-flow__planner-link" to={plannerHref}>
            <CalendarDays size={15} /> Open in Planner
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
            onClick={() => {
              void programmesQuery.refetch();
              void universeQuery.refetch();
              void queueQuery.refetch();
              void optimizerQuery.refetch();
            }}
          >
            <RefreshCw size={15} /> Refresh
          </button>
          {canManage && programmes.length ? (
            <button type="button" className="is-primary" onClick={() => setShowCreate(true)}>
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
            <strong>{tab.label}</strong>
            <small>{tab.hint}</small>
          </button>
        ))}
      </nav>

      {error ? (
        <div className="qms-audit-programme__error" role="alert">
          <AlertTriangle size={16} /> {error instanceof Error ? error.message : "Audit programme data could not be loaded."}
        </div>
      ) : null}

      {workspaceTab === "portfolio" || workspaceTab === "requirements" || workspaceTab === "readiness" ? (
        !programmesQuery.isLoading && !programmes.length ? (
          <div className="qms-audit-programme-flow__empty qms-audit-programme-flow__empty--portfolio" role="status">
            <div>
              <strong>No programme for {year}</strong>
              <p>Create a draft to define coverage, requirements, and readiness for this year.</p>
            </div>
            {canManage ? (
              <button type="button" className="is-primary" onClick={() => setShowCreate(true)}>
                <Plus size={15} /> Create programme
              </button>
            ) : (
              <small>Audit manage permission is required to create a programme.</small>
            )}
          </div>
        ) : (
        <div className="qms-audit-programme__workspace qms-audit-programme-flow__workspace">
          <aside className="qms-audit-programme__portfolio" hidden={workspaceTab !== "portfolio" && workspaceTab !== "requirements" && workspaceTab !== "readiness"}>
            <header>
              <strong>Portfolio</strong>
              <small>
                {programmes.length} · {year}
              </small>
            </header>
            {programmesQuery.isLoading ? (
              <p className="qms-audit-programme-flow__empty">Loading programmes…</p>
            ) : (
              programmes.map((programme) => {
                const unscheduled = programme.readiness?.unscheduled_requirement_count ?? programme.metrics?.unscheduled_audit_count;
                const scheduled = programme.metrics?.scheduled_audit_count;
                const planned = programme.metrics?.planned_audit_count;
                return (
                  <button
                    key={programme.id}
                    type="button"
                    className={`qms-audit-programme-flow__portfolio-card${programme.id === selectedProgrammeId ? " is-active" : ""}`}
                    onClick={() => {
                      setSelectedId(programme.id);
                      if (workspaceTab === "portfolio") setWorkspaceTab("requirements");
                    }}
                  >
                    <span className="qms-audit-programme-flow__portfolio-card-top">
                      <strong title={programme.title}>{programme.title}</strong>
                      <b className={`qms-chip qms-chip--${statusTone(programme.status)}`}>{human(programme.status)}</b>
                    </span>
                    <small title={`${programme.programme_ref} · ${methodologyLabel(programme.assurance_model)} · Rev ${programme.revision_no}`}>
                      <span className="qms-audit-programme-flow__ref">{programme.programme_ref}</span>
                      {" · "}
                      {methodologyLabel(programme.assurance_model)}
                      {" · Rev "}
                      {programme.revision_no}
                    </small>
                    <span className="qms-audit-programme-flow__portfolio-metrics">
                      <span>{dateLabel(programme.period_start)} → {dateLabel(programme.period_end)}</span>
                      <span>{typeof planned === "number" ? `${planned} audits` : "—"}</span>
                      <span>{typeof scheduled === "number" ? `${scheduled} scheduled` : "—"}</span>
                      <span className={unscheduled ? "is-warn" : ""}>
                        {typeof unscheduled === "number" ? `${unscheduled} unscheduled` : "Readiness n/a"}
                      </span>
                    </span>
                  </button>
                );
              })
            )}
          </aside>

          <section className="qms-audit-programme__detail">
            {!selectedProgrammeId ? (
              <div className="qms-audit-programme-flow__empty qms-audit-programme-flow__empty--inline">
                <p>Select a programme revision from the portfolio.</p>
              </div>
            ) : detailQuery.isLoading ? (
              <p className="qms-audit-programme-flow__empty">Loading programme…</p>
            ) : !selected ? (
              <p className="qms-audit-programme-flow__empty">Programme not available.</p>
            ) : (
              <>
                <header className="qms-audit-programme__detail-header">
                  <div>
                    <span>
                      <b className="qms-audit-programme-flow__ref">{selected.programme_ref}</b>
                      <small> · Rev {selected.revision_no}</small>
                    </span>
                    <h2 title={selected.title}>{selected.title}</h2>
                    <p>
                      {dateLabel(selected.period_start)} → {dateLabel(selected.period_end)}
                    </p>
                  </div>
                  <div className="qms-audit-programme-flow__detail-actions">
                    <span className={`qms-chip qms-chip--${statusTone(selected.status)}`}>{human(selected.status)}</span>
                    <button type="button" onClick={() => setShowProgrammeDetail(true)}>
                      Details
                    </button>
                    {canManage && programmeEditable(selected.status) ? (
                      <button type="button" onClick={() => openProgrammeEdit(selected)}>
                        <Pencil size={14} /> Edit
                      </button>
                    ) : null}
                  </div>
                </header>

                {(workspaceTab === "portfolio" || workspaceTab === "requirements") && (
                  <section className="qms-audit-programme-flow__basis qms-audit-programme-flow__basis--compact" aria-label="Programme summary">
                    <div className="is-risk">
                      <span>Methodology</span>
                      <strong>
                        <Activity size={15} /> {methodologyLabel(selectedModel)}
                        {selected.continuous_monitoring_enabled ? " · Continuous" : ""}
                      </strong>
                      <div className="qms-audit-programme-flow__method-pillars" aria-label="Methodology pillars">
                        {METHODOLOGY_PILLARS.map((pillar) => {
                          const weight =
                            pillar.id === "COMPLIANCE"
                              ? optimizer?.weights?.compliance
                              : pillar.id === "RISK"
                                ? optimizer?.weights?.risk
                                : optimizer?.weights?.performance;
                          const active =
                            selectedModel === "HYBRID" ||
                            selectedModel === pillar.id ||
                            (selectedModel === "COMPLIANCE" && pillar.id === "COMPLIANCE");
                          return (
                            <span key={pillar.id} className={active ? "is-active" : ""}>
                              <b>{pillar.label}</b>
                              <small>
                                {typeof weight === "number" ? `${Math.round(weight * 100)}%` : pillar.hint}
                              </small>
                            </span>
                          );
                        })}
                      </div>
                    </div>
                    <dl>
                      <div>
                        <dt>Requirements</dt>
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
                )}

                {workspaceTab === "requirements" ? (
                  <>
                    <section
                      className="qms-audit-programme-flow__queue qms-audit-programme-flow__queue--compact"
                      aria-label={`${methodologyLabel(selectedModel)} assurance optimizer`}
                    >
                      <header>
                        <div>
                          <strong>
                            <BrainCircuit size={15} /> Optimizer
                          </strong>
                          <small>Compliance · risk · performance scoring</small>
                        </div>
                        {canManage ? (
                          <button type="button" disabled={optimizerMutation.isPending} onClick={() => optimizerMutation.mutate()}>
                            <RefreshCw size={14} />{" "}
                            {["DRAFT", "UNDER_REVIEW"].includes(selected.status)
                              ? "Recalculate & sync"
                              : "Recalculate"}
                          </button>
                        ) : null}
                      </header>
                      {optimizerQuery.isLoading ? (
                        <p className="qms-audit-programme-flow__empty">Calculating current surveillance priorities…</p>
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

                    <section className="qms-audit-programme__requirements qms-audit-programme-flow__coverage">
                      <header>
                        <div>
                          <strong>
                            <Target size={15} /> Requirements
                          </strong>
                          <small>Schedule from programme · dates only in Planner V2</small>
                        </div>
                        <div className="qms-audit-programme-flow__coverage-actions">
                          <Link to={plannerHref}>
                            Open in Planner <ArrowRight size={14} />
                          </Link>
                          {canManage && ["DRAFT", "UNDER_REVIEW"].includes(selected.status) ? (
                            <button type="button" onClick={() => setShowRequirement(true)}>
                              <Plus size={14} /> Add coverage
                            </button>
                          ) : null}
                        </div>
                      </header>

                      {!selected.items?.length ? (
                        <div className="qms-audit-programme-flow__empty">
                          <p>No coverage yet. Add universe entities, then sync optimizer coverage.</p>
                        </div>
                      ) : (
                        <DataTableShell title="Programme requirements">
                          <div className="qms-audit-programme__table-wrap qms-audit-programme__table-wrap--dense">
                            <table>
                              <thead>
                                <tr>
                                  <th>Source / entity</th>
                                  <th>Regulatory basis</th>
                                  <th>Frequency</th>
                                  <th>Coverage</th>
                                  <th>Schedule</th>
                                  <th>Next target</th>
                                  <th>Owner</th>
                                  <th>Actions</th>
                                </tr>
                              </thead>
                              <tbody>
                                {selected.items.map((item) => {
                                  const link = linksByItem.get(item.id);
                                  const hybrid = (item.prioritization_basis || []).find(
                                    (basis) => String(basis.driver || "") === "HYBRID_ASSURANCE",
                                  );
                                  const driver = hybrid
                                    ? `${methodologyLabel(selectedModel)} ${String(hybrid.priority_score || "—")}`
                                    : human(String(item.prioritization_basis?.[0]?.driver || "Judgement"));
                                  const isUnscheduled = item.state === "PLANNED";
                                  const regulatory = linesOf(item.criteria) || item.scope || "—";
                                  return (
                                    <tr key={item.id} className={isUnscheduled ? "is-unscheduled" : ""}>
                                      <td>
                                        <strong title={item.title}>{item.title}</strong>
                                        <small title={`${item.auditable_entity?.display_label || "Unlinked entity"} · ${human(item.audit_type)}`}>
                                          {item.auditable_entity?.display_label || "Unlinked entity"} · {human(item.audit_type)}
                                          {item.mandatory_surveillance ? " · Mandatory" : ""}
                                        </small>
                                      </td>
                                      <td>
                                        <span className="qms-audit-programme-flow__cell-clip" title={regulatory}>{regulatory}</span>
                                        <small>{driver}</small>
                                      </td>
                                      <td>{human(item.recurrence)}</td>
                                      <td>
                                        {item.mandatory_surveillance
                                          ? "Mandatory floor"
                                          : `Risk ${human(item.auditable_entity?.risk_classification || "MEDIUM")}`}
                                      </td>
                                      <td>
                                        <span className={`qms-chip qms-chip--${statusTone(item.state)}`}>{human(item.state)}</span>
                                        {link?.next_due_date ? (
                                          <small>Due {dateLabel(link.next_due_date)}</small>
                                        ) : (
                                          <small className="is-muted">No planner commitment</small>
                                        )}
                                      </td>
                                      <td>
                                        {dateLabel(item.target_start)}
                                        <small>to {dateLabel(item.target_end)}</small>
                                      </td>
                                      <td>
                                        <small>{item.auditable_entity?.source_owner_module || "—"}</small>
                                      </td>
                                      <td className="qms-audit-programme-flow__row-actions">
                                        <button type="button" className="is-ghost" onClick={() => openRequirementDrawer(item, false)}>
                                          Details
                                        </button>
                                        {canManage && programmeEditable(selected.status) ? (
                                          <button type="button" className="is-ghost" onClick={() => openRequirementDrawer(item, true)}>
                                            <Pencil size={14} /> Edit
                                          </button>
                                        ) : null}
                                        {isUnscheduled ? (
                                          canManage ? (
                                            <button type="button" onClick={() => openSchedule(selected.id, item.id)}>
                                              Schedule <CalendarClock size={14} />
                                            </button>
                                          ) : (
                                            <span title="Requires audit manage permission">Schedule unavailable</span>
                                          )
                                        ) : (
                                          <Link to={plannerHref}>
                                            Planner <CalendarDays size={14} />
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

                    <section className="qms-audit-programme-flow__queue" aria-label="Programme scheduling queue">
                      <header>
                        <div>
                          <strong>
                            <CalendarClock size={16} /> Needs scheduling
                          </strong>
                          <small>Approved or active requirements waiting for an authoritative Planner commitment.</small>
                        </div>
                      </header>
                      {!queue.length ? (
                        <p className="qms-audit-programme-flow__empty">
                          {selected.status === "DRAFT" || selected.status === "UNDER_REVIEW"
                            ? "Scheduling becomes available after programme approval."
                            : "No approved requirements are waiting for scheduling."}
                        </p>
                      ) : (
                        <div>
                          {queue.map((item) =>
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
                                <small>
                                  {SCHEDULABLE_RECURRENCES.has(item.recurrence)
                                    ? canManage
                                      ? `${dateLabel(item.target_start)} → ${dateLabel(item.target_end)} · ${human(item.recurrence)}`
                                      : "Scheduling requires audit manage permission."
                                    : `${human(item.recurrence)} requires a governed occurrence trigger.`}
                                </small>
                              </span>
                            ),
                          )}
                        </div>
                      )}
                    </section>
                  </>
                ) : null}

                {workspaceTab === "readiness" ? (
                  <>
                    <section
                      className={`qms-audit-programme-flow__readiness ${readiness.ready_for_approval ? "is-ready" : "is-blocked"}`}
                      aria-label="Programme approval readiness"
                    >
                      <div>
                        {readiness.ready_for_approval ? <CheckCircle2 size={18} /> : <TriangleAlert size={18} />}
                        <span>
                          <strong>
                            {readiness.ready_for_approval ? "Ready for approval review" : "Setup incomplete"}
                          </strong>
                          <small>
                            {readiness.ready_for_approval
                              ? `${human(selected.status)} · approval can freeze this revision`
                              : `${readiness.blockers.length} blocker${readiness.blockers.length === 1 ? "" : "s"} before approval`}
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

                    <section className="qms-audit-programme-flow__readiness-grid" aria-label="Readiness signals">
                      <article>
                        <span>Unscheduled requirements</span>
                        <strong>{readiness.unscheduled_requirement_count}</strong>
                        <small>
                          {unscheduledItems.length
                            ? `${unscheduledItems.slice(0, 3).map((item) => item.title).join(" · ")}${unscheduledItems.length > 3 ? "…" : ""}`
                            : "None in current revision"}
                        </small>
                      </article>
                      <article>
                        <span>Coverage gaps</span>
                        <strong>{coverageGapCount ?? "—"}</strong>
                        <small>
                          {coverageGapCount == null
                            ? optimizerQuery.isLoading
                              ? "Loading optimizer…"
                              : "Optimizer gap count not available"
                            : coverageGapCount
                              ? "Entities recommended but not covered"
                              : "No optimizer coverage gaps"}
                        </small>
                      </article>
                      <article>
                        <span>Missing mappings</span>
                        <strong>{missingMappingItems.length}</strong>
                        <small>
                          {missingMappingItems.length
                            ? "Requirements without an auditable entity link"
                            : "All requirements mapped to universe entities"}
                        </small>
                      </article>
                      <article>
                        <span>Approval state</span>
                        <strong className={`qms-chip qms-chip--${statusTone(selected.status)}`}>{human(selected.status)}</strong>
                        <small>
                          {selected.approved_at
                            ? `Approved ${dateLabel(selected.approved_at.slice(0, 10))}`
                            : selected.status === "UNDER_REVIEW"
                              ? "Awaiting approval decision"
                              : "Not approved yet"}
                        </small>
                      </article>
                      <article>
                        <span>Scheduling conflicts</span>
                        <strong>—</strong>
                        <small>Conflicts surface when creating a Planner schedule from a requirement</small>
                      </article>
                      <article>
                        <span>Mandatory unscheduled</span>
                        <strong>{readiness.mandatory_unscheduled_count}</strong>
                        <small>
                          {readiness.mandatory_requirement_count
                            ? `${readiness.mandatory_requirement_count} mandatory in programme`
                            : "No mandatory requirements reported"}
                        </small>
                      </article>
                    </section>

                    {transitionTargets(selected.status).length ||
                    (selected.status !== "DRAFT" && selected.status !== "SUPERSEDED" && canManage) ? (
                      <section className="qms-audit-programme__governance qms-audit-programme-flow__approval">
                        <div>
                          <strong>
                            <ShieldCheck size={15} /> Review and approve
                          </strong>
                          <p>Approval freezes this revision. Amendments handle later coverage changes.</p>
                        </div>
                        <div className="qms-audit-programme__actions">
                          <input
                            aria-label="Programme transition reason"
                            value={actionReason}
                            onChange={(event) => setActionReason(event.target.value)}
                            placeholder="Decision / amendment reason"
                          />
                          {transitionTargets(selected.status).map((target) => (
                            <button
                              key={target}
                              type="button"
                              disabled={
                                !canManage ||
                                actionReason.trim().length < 3 ||
                                transitionMutation.isPending ||
                                (target === "APPROVED" && !readiness.ready_for_approval)
                              }
                              onClick={() => transitionMutation.mutate(target)}
                            >
                              {target === "UNDER_REVIEW" ? "Submit for review" : human(target)} <ArrowRight size={14} />
                            </button>
                          ))}
                          {selected.status !== "DRAFT" && selected.status !== "SUPERSEDED" && canManage ? (
                            <button
                              type="button"
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

                {workspaceTab === "portfolio" ? (
                  <section className="qms-audit-programme-flow__basis qms-audit-programme-flow__basis--compact" aria-label="Portfolio summary">
                    <div>
                      <span>Portfolio</span>
                      <strong>
                        <Gauge size={15} /> Coverage then Planner dates
                      </strong>
                      <p>Select a revision. Requirements define coverage; Readiness gates approval.</p>
                    </div>
                    <dl>
                      <div>
                        <dt>Universe</dt>
                        <dd>{universeQuery.data?.total ?? universeQuery.data?.items?.length ?? "—"}</dd>
                      </div>
                      <div>
                        <dt>Queue</dt>
                        <dd>{queue.length}</dd>
                      </div>
                      <div>
                        <dt>Scheduled</dt>
                        <dd>{scheduledCount}</dd>
                      </div>
                      <div>
                        <dt>Gaps</dt>
                        <dd>{coverageGaps}</dd>
                      </div>
                    </dl>
                  </section>
                ) : null}
              </>
            )}
          </section>
        </div>
        )
      ) : null}

      {workspaceTab === "universe" ? (
        <section className="qms-audit-programme__universe qms-audit-programme-flow__universe" aria-labelledby="qms-audit-universe-heading">
          <header>
            <div>
              <h2 id="qms-audit-universe-heading">
                <Library size={14} /> Audit Universe
              </h2>
              <p>Entities feeding coverage recommendations.</p>
            </div>
            {canManage ? (
              <button type="button" onClick={() => setShowUniverseCreate(true)}>
                <Plus size={14} /> Add entity
              </button>
            ) : null}
          </header>
          {universeQuery.isLoading ? (
            <p className="qms-audit-programme-flow__empty">Loading Audit Universe…</p>
          ) : !(universeQuery.data?.items || []).length ? (
            <div className="qms-audit-programme-flow__empty">
              <p>No auditable entities yet.</p>
              {canManage ? (
                <button type="button" onClick={() => setShowUniverseCreate(true)}>
                  <Plus size={14} /> Add first entity
                </button>
              ) : null}
            </div>
          ) : (
          <div className="qms-audit-programme__table-wrap qms-audit-programme__table-wrap--dense">
            <table>
              <thead>
                <tr>
                  <th>Entity / type</th>
                  <th>Scope / source</th>
                  <th>Risk / priority</th>
                  <th>Linked requirements</th>
                  <th>Schedule status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {(universeQuery.data?.items || []).map((item) => {
                  const linked = linkedRequirementCount(item.id);
                  const linkedItems = (selected?.items || []).filter((req) => req.universe_item_id === item.id);
                  const scheduledLinked = linkedItems.filter((req) => req.state === "SCHEDULED" || req.state === "COMPLETED").length;
                  const unscheduledLinked = linkedItems.filter((req) => req.state === "PLANNED").length;
                  return (
                    <tr key={item.id}>
                      <td>
                        <strong title={item.display_label}>{item.display_label}</strong>
                        <small>{human(item.entity_type)}{item.mandatory_surveillance ? " · Mandatory" : ""}{!item.active ? " · Inactive" : ""}</small>
                      </td>
                      <td>
                        <small title={`${item.source_owner_module} · ${item.source_type}${item.notes ? ` · ${item.notes}` : ""}`}>
                          {item.source_owner_module} · {item.source_type}
                          {item.notes ? ` · ${item.notes}` : ""}
                        </small>
                      </td>
                      <td>
                        <span className="qms-chip">{human(item.risk_classification)}</span>
                        <small>Criticality {human(item.regulatory_criticality)}</small>
                      </td>
                      <td>
                        <strong>{linked}</strong>
                        <small>{selectedProgrammeId ? "In selected programme" : "Select a programme"}</small>
                      </td>
                      <td>
                        {linked ? (
                          <>
                            <span className={`qms-chip${unscheduledLinked ? " qms-chip--warn" : " qms-chip--good"}`}>
                              {scheduledLinked} scheduled · {unscheduledLinked} open
                            </span>
                          </>
                        ) : (
                          <small className="is-muted">Not in programme coverage</small>
                        )}
                      </td>
                      <td className="qms-audit-programme-flow__row-actions">
                        <button type="button" className="is-ghost" onClick={() => openUniverseDrawer(item, false)}>Details</button>
                        {canManage ? (
                          <button type="button" className="is-ghost" onClick={() => openUniverseDrawer(item, true)}>
                            <Pencil size={12} /> Edit
                          </button>
                        ) : null}
                        {item.source_route ? <Link to={item.source_route}>Source</Link> : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          )}
        </section>
      ) : null}

      <Drawer title="Create programme" isOpen={showCreate} onClose={() => setShowCreate(false)} side="right" panelClassName="qms-audit-programme-drawer">
        <form
          className="qms-audit-programme__form qms-audit-programme-flow__create"
          onSubmit={(event) => {
            event.preventDefault();
            createProgrammeMutation.mutate();
          }}
        >
          <header>
            <strong>Create programme</strong>
            <small>Hybrid methodology · coverage here · dates in Planner after approval</small>
          </header>
          <div className="qms-audit-programme-flow__methodologies qms-audit-programme-flow__methodologies--readonly" role="group" aria-label="Methodology pillars">
            {METHODOLOGY_PILLARS.map((pillar) => (
              <div key={pillar.id} className="is-selected">
                <strong>{pillar.label}</strong>
                <small>{pillar.hint}</small>
              </div>
            ))}
            <div className="is-selected">
              <strong>Hybrid</strong>
              <small>Active model — combines all three pillars</small>
            </div>
          </div>
          <label className="is-wide">
            <span>Programme title</span>
            <input
              required
              minLength={3}
              value={programmeForm.title}
              onChange={(event) => setProgrammeForm((current) => ({ ...current, title: event.target.value }))}
            />
          </label>
          <label>
            <span>Programme start</span>
            <input
              required
              type="date"
              value={programmeForm.period_start}
              onChange={(event) => setProgrammeForm((current) => ({ ...current, period_start: event.target.value }))}
            />
          </label>
          <label>
            <span>Programme end</span>
            <input
              required
              type="date"
              value={programmeForm.period_end}
              onChange={(event) => setProgrammeForm((current) => ({ ...current, period_end: event.target.value }))}
            />
          </label>
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
          <footer>
            <button type="button" onClick={() => setShowCreate(false)}>
              Cancel
            </button>
            <button className="is-primary" disabled={createProgrammeMutation.isPending}>
              Create draft programme
            </button>
          </footer>
        </form>
      </Drawer>

      <Drawer
        title="Add coverage"
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
            <span>Additional human driver</span>
            <select
              value={itemForm.driver}
              onChange={(event) =>
                setItemForm((current) => ({ ...current, driver: event.target.value as (typeof DRIVERS)[number] }))
              }
            >
              {DRIVERS.map((value) => (
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
            <span>Purpose / reason for additional coverage</span>
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
          <footer>
            <button type="button" onClick={() => setShowRequirement(false)}>
              Cancel
            </button>
            <button className="is-primary" disabled={itemMutation.isPending}>
              Add to programme
            </button>
          </footer>
        </form>
      </Drawer>

      <Drawer
        title="Add auditable entity"
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
            <span>Authoritative source module</span>
            <input
              required
              value={universeForm.source_owner_module}
              onChange={(event) => setUniverseForm((current) => ({ ...current, source_owner_module: event.target.value }))}
            />
          </label>
          <label>
            <span>Source record type</span>
            <input
              required
              value={universeForm.source_type}
              onChange={(event) => setUniverseForm((current) => ({ ...current, source_type: event.target.value }))}
            />
          </label>
          <label>
            <span>Source record ID</span>
            <input
              required
              value={universeForm.source_id}
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
            <span>Inherent risk</span>
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
          <label className="is-wide">
            <span>Notes</span>
            <textarea
              rows={2}
              value={universeForm.notes}
              onChange={(event) => setUniverseForm((current) => ({ ...current, notes: event.target.value }))}
            />
          </label>
          <footer>
            <button type="button" onClick={() => setShowUniverseCreate(false)}>
              Cancel
            </button>
            <button className="is-primary" disabled={universeMutation.isPending}>
              Add entity
            </button>
          </footer>
        </form>
      </Drawer>

      <Drawer
        title="Programme details"
        isOpen={showProgrammeDetail}
        onClose={() => setShowProgrammeDetail(false)}
        side="right"
        panelClassName="qms-audit-programme-drawer"
      >
        {selected ? (
          <div className="qms-audit-programme-flow__drawer-summary">
            <header>
              <strong title={selected.title}>{selected.title}</strong>
              <small>
                {selected.programme_ref} · Rev {selected.revision_no} · {human(selected.status)}
              </small>
            </header>
            <dl>
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
                <dt>Requirements</dt>
                <dd>{readiness.requirement_count}</dd>
              </div>
              <div>
                <dt>Unscheduled</dt>
                <dd>{readiness.unscheduled_requirement_count}</dd>
              </div>
            </dl>
            <footer>
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
              ) : (
                <p className="qms-audit-programme-flow__drawer-note">
                  Approved or active revisions are immutable. Create an amendment to change coverage fields.
                </p>
              )}
              <button type="button" onClick={() => setShowProgrammeDetail(false)}>
                Close
              </button>
            </footer>
          </div>
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
          <p className="qms-audit-programme-flow__drawer-note">
            Editable via API while DRAFT or UNDER_REVIEW: title, period, objectives, and regulatory basis. A change reason is required.
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
          <footer>
            <button type="button" onClick={() => setShowProgrammeEdit(false)}>
              Cancel
            </button>
            <button type="submit" className="is-primary" disabled={updateProgrammeMutation.isPending || editReason.trim().length < 3}>
              Save programme
            </button>
          </footer>
        </form>
      </Drawer>

      <Drawer
        title={requirementEditMode ? "Edit requirement" : "Requirement details"}
        isOpen={Boolean(requirementFocus)}
        onClose={() => {
          setRequirementFocus(null);
          setRequirementEditMode(false);
        }}
        side="right"
        panelClassName="qms-audit-programme-drawer"
      >
        {requirementFocus && !requirementEditMode ? (
          <div className="qms-audit-programme-flow__drawer-summary">
            <header>
              <strong title={requirementFocus.title}>{requirementFocus.title}</strong>
              <small>
                {human(requirementFocus.audit_type)} · {human(requirementFocus.state)}
              </small>
            </header>
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
                <dt>Schedule ref</dt>
                <dd>{linksByItem.get(requirementFocus.id)?.schedule_id?.slice(0, 8) || "Not scheduled"}</dd>
              </div>
            </dl>
            <footer>
              {canManage && selected && programmeEditable(selected.status) ? (
                <button type="button" className="is-primary" onClick={() => openRequirementDrawer(requirementFocus, true)}>
                  <Pencil size={14} /> Edit requirement
                </button>
              ) : (
                <p className="qms-audit-programme-flow__drawer-note">
                  Requirement edits require a DRAFT or UNDER_REVIEW programme revision.
                </p>
              )}
              <button
                type="button"
                onClick={() => {
                  setRequirementFocus(null);
                  setRequirementEditMode(false);
                }}
              >
                Close
              </button>
            </footer>
          </div>
        ) : null}
        {requirementFocus && requirementEditMode ? (
          <form
            className="qms-audit-programme__form qms-audit-programme-flow__create"
            onSubmit={(event) => {
              event.preventDefault();
              updateItemMutation.mutate();
            }}
          >
            <p className="qms-audit-programme-flow__drawer-note">
              Patchable fields: title, purpose, scope, criteria, recurrence, mandatory flag, and target window. Change reason required.
            </p>
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
            <footer>
              <button
                type="button"
                onClick={() => {
                  setRequirementFocus(null);
                  setRequirementEditMode(false);
                }}
              >
                Cancel
              </button>
              <button type="submit" className="is-primary" disabled={updateItemMutation.isPending || editReason.trim().length < 3}>
                Save requirement
              </button>
            </footer>
          </form>
        ) : null}
      </Drawer>

      <Drawer
        title={universeEditMode ? "Edit universe entity" : "Universe entity"}
        isOpen={Boolean(universeFocus)}
        onClose={() => {
          setUniverseFocus(null);
          setUniverseEditMode(false);
        }}
        side="right"
        panelClassName="qms-audit-programme-drawer"
      >
        {universeFocus && !universeEditMode ? (
          <div className="qms-audit-programme-flow__drawer-summary">
            <header>
              <strong>{universeFocus.display_label}</strong>
              <small>
                {human(universeFocus.entity_type)} · {universeFocus.active ? "Active" : "Inactive"}
              </small>
            </header>
            <dl>
              <div>
                <dt>Source</dt>
                <dd>
                  {universeFocus.source_owner_module} · {universeFocus.source_type} · {universeFocus.source_id}
                </dd>
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
                <dt>Notes</dt>
                <dd>{universeFocus.notes || "—"}</dd>
              </div>
            </dl>
            <footer>
              {canManage ? (
                <button type="button" className="is-primary" onClick={() => openUniverseDrawer(universeFocus, true)}>
                  <Pencil size={14} /> Edit entity
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => {
                  setUniverseFocus(null);
                  setUniverseEditMode(false);
                }}
              >
                Close
              </button>
            </footer>
          </div>
        ) : null}
        {universeFocus && universeEditMode ? (
          <form
            className="qms-audit-programme__form qms-audit-programme-flow__create"
            onSubmit={(event) => {
              event.preventDefault();
              updateUniverseMutation.mutate();
            }}
          >
            <p className="qms-audit-programme-flow__drawer-note">
              Patchable: label, route, risk, criticality, interval, mandatory flag, active state, and notes. Source identity is read-only.
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
            <footer>
              <button
                type="button"
                onClick={() => {
                  setUniverseFocus(null);
                  setUniverseEditMode(false);
                }}
              >
                Cancel
              </button>
              <button type="submit" className="is-primary" disabled={updateUniverseMutation.isPending}>
                Save entity
              </button>
            </footer>
          </form>
        ) : null}
      </Drawer>

      <Drawer
        title="Schedule into Planner V2"
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
              /* stay open so user can hand off to Planner from success panel */
            }}
          />
        ) : null}
      </Drawer>
    </div>
  );
};

export default QmsAuditProgrammePageV2;
