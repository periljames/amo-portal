import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Gauge,
  Library,
  Plus,
  RefreshCw,
  ShieldCheck,
  Target,
  TriangleAlert,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { hasQmsRolePermission } from "../../app/routeGuards";
import {
  addAuditProgrammeItem,
  createAuditProgramme,
  createAuditProgrammeAmendment,
  createAuditUniverseItem,
  getAuditProgramme,
  listAuditProgrammeScheduleLinks,
  listAuditProgrammeSchedulingQueue,
  listAuditProgrammes,
  listAuditUniverse,
  transitionAuditProgramme,
  type AuditProgramme,
  type AuditProgrammeList,
  type AuditProgrammeMethodology,
  type AuditProgrammeStatus,
  type AuditRiskLevel,
  type AuditUniverseEntityType,
} from "../../services/qmsAuditProgramme";
import "../../styles/qms-audit-programme.css";
import "../../styles/qms-audit-programme-workflow.css";

const AUDIT_SUBJECTS = [
  "INTERNAL", "DEPARTMENTAL", "TECHNICAL", "WORK_PACK", "SUPPLIER", "CONTRACTED_FUNCTION",
  "FACILITY", "PERSONNEL", "PRODUCT", "PROCESS", "REGULATORY", "SPECIAL", "REACTIVE", "FOLLOW_UP",
] as const;
const RECURRENCES = ["ONE_TIME", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL", "CUSTOM", "RISK_TRIGGERED"] as const;
const DRIVERS = [
  "REGULATORY_REQUIREMENT", "PROCESS_IMPORTANCE", "CHANGE", "PRIOR_FINDINGS",
  "KPI_PERFORMANCE", "SAFETY_RISK", "SUPPLIER_PERFORMANCE",
] as const;
const UNIVERSE_TYPES: AuditUniverseEntityType[] = ["DEPARTMENT", "FACILITY", "STATION", "SUPPLIER", "CONTRACTOR", "PROCESS", "CAPABILITY", "APPROVAL_RATING", "AIRCRAFT_TYPE", "PERSONNEL_GROUP", "OTHER"];
const RISKS: AuditRiskLevel[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const SCHEDULABLE_RECURRENCES = new Set(["ONE_TIME", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL"]);

const METHODOLOGIES: Array<{
  value: AuditProgrammeMethodology;
  title: string;
  description: string;
  driver: typeof DRIVERS[number];
  icon: React.ComponentType<{ size?: number }>;
}> = [
  {
    value: "COMPLIANCE",
    title: "Compliance based",
    description: "Starts with regulations, approvals, manuals, contractual requirements and required surveillance intervals.",
    driver: "REGULATORY_REQUIREMENT",
    icon: ShieldCheck,
  },
  {
    value: "PERFORMANCE",
    title: "Performance based",
    description: "Starts with process results, KPIs, repeat defects, effectiveness and operational performance trends.",
    driver: "KPI_PERFORMANCE",
    icon: Gauge,
  },
  {
    value: "RISK",
    title: "Risk based",
    description: "Prioritises safety and business risk, change, previous findings, events and emerging assurance signals.",
    driver: "SAFETY_RISK",
    icon: TriangleAlert,
  },
];

const MONTHS = Array.from({ length: 12 }, (_, index) => new Date(2026, index, 1).toLocaleDateString(undefined, { month: "short" }));

function human(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateLabel(value?: string | null): string {
  if (!value) return "Not set";
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function transitionTargets(status: AuditProgrammeStatus): AuditProgrammeStatus[] {
  if (status === "DRAFT") return ["UNDER_REVIEW"];
  if (status === "UNDER_REVIEW") return ["DRAFT", "APPROVED"];
  if (status === "APPROVED") return ["ACTIVE", "SUPERSEDED"];
  if (status === "ACTIVE") return ["SUPERSEDED", "CLOSED"];
  return [];
}

function methodologyOf(programme?: AuditProgramme): AuditProgrammeMethodology {
  return programme?.programme_methodology || "COMPLIANCE";
}

function readinessOf(programme?: AuditProgramme) {
  if (programme?.readiness) return programme.readiness;
  const items = programme?.items || [];
  const blockers: Array<{ code: string; message: string }> = [];
  if (!items.length) blockers.push({ code: "NO_REQUIREMENTS", message: "Add at least one governed audit requirement before approval." });
  items.forEach((item) => {
    if (!item.target_start || !item.target_end) blockers.push({ code: "MISSING_TARGET_WINDOW", message: `${item.title}: set a target window.` });
    if (!item.criteria?.length) blockers.push({ code: "MISSING_CRITERIA", message: `${item.title}: add audit criteria.` });
  });
  return {
    ready_for_approval: blockers.length === 0,
    blockers,
    requirement_count: items.length,
    mandatory_requirement_count: items.filter((item) => item.mandatory_surveillance).length,
    mandatory_unscheduled_count: items.filter((item) => item.mandatory_surveillance && item.state === "PLANNED").length,
    high_risk_requirement_count: items.filter((item) => ["HIGH", "CRITICAL"].includes(item.auditable_entity?.risk_classification || "")).length,
    unscheduled_requirement_count: items.filter((item) => item.state === "PLANNED").length,
  };
}

const QmsAuditProgrammePageV2: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const queryClient = useQueryClient();
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showRequirement, setShowRequirement] = useState(false);
  const [showUniverseCreate, setShowUniverseCreate] = useState(false);
  const [actionReason, setActionReason] = useState("");
  const canManage = hasQmsRolePermission("qms.audit.manage");

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
  const scheduleLinksQuery = useQuery({
    queryKey: ["qms-audit-programme-schedule-links", amoCode, selectedProgrammeId],
    queryFn: ({ signal }) => listAuditProgrammeScheduleLinks(amoCode, selectedProgrammeId as string, signal),
    enabled: Boolean(selectedProgrammeId),
    staleTime: 3_000,
  });
  const selected = detailQuery.data;
  const readiness = readinessOf(selected);
  const selectedMethodology = methodologyOf(selected);

  const [programmeForm, setProgrammeForm] = useState({
    title: `${currentYear} Quality Audit Programme`,
    programme_methodology: "COMPLIANCE" as AuditProgrammeMethodology,
    methodology_rationale: "",
    period_start: `${currentYear}-01-01`,
    period_end: `${currentYear}-12-31`,
    objectives: "Verify continuing conformity and effectiveness of the Quality system.",
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
    driver: "REGULATORY_REQUIREMENT" as typeof DRIVERS[number],
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

  const invalidateProgramme = async (programmeId?: string) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-programmes", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-programme", amoCode, programmeId || selectedProgrammeId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-programme-scheduling-queue", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-programme-schedule-links", amoCode, programmeId || selectedProgrammeId] }),
    ]);
  };

  const createProgrammeMutation = useMutation({
    mutationFn: () => createAuditProgramme(amoCode, {
      programme_year: year,
      title: programmeForm.title.trim(),
      programme_methodology: programmeForm.programme_methodology,
      methodology_rationale: programmeForm.methodology_rationale.trim() || undefined,
      objectives: programmeForm.objectives.split("\n").map((value) => value.trim()).filter(Boolean),
      regulatory_basis: programmeForm.regulatory_basis.split("\n").map((value) => value.trim()).filter(Boolean),
      period_start: programmeForm.period_start,
      period_end: programmeForm.period_end,
    }),
    onSuccess: async (programme) => {
      setSelectedId(programme.id);
      setShowCreate(false);
      await invalidateProgramme(programme.id);
    },
  });

  const transitionMutation = useMutation({
    mutationFn: (target: AuditProgrammeStatus) => transitionAuditProgramme(amoCode, selectedProgrammeId as string, target, actionReason.trim()),
    onSuccess: (programme) => {
      setActionReason("");
      queryClient.setQueryData(["qms-audit-programme", amoCode, programme.id], programme);
      queryClient.setQueryData<AuditProgrammeList>(["qms-audit-programmes", amoCode, year], (current) => current ? {
        ...current,
        items: current.items.map((item) => item.id === programme.id ? programme : item),
      } : current);
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
    mutationFn: () => addAuditProgrammeItem(amoCode, selectedProgrammeId as string, {
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
      prioritization_basis: [{ driver: itemForm.driver, programme_methodology: selectedMethodology }],
    }),
    onSuccess: async () => {
      setShowRequirement(false);
      setItemForm((current) => ({ ...current, title: "", purpose: "", scope: "", criteria: "", target_start: "", target_end: "" }));
      await invalidateProgramme();
    },
  });

  const universeMutation = useMutation({
    mutationFn: () => createAuditUniverseItem(amoCode, {
      entity_type: universeForm.entity_type,
      display_label: universeForm.display_label.trim(),
      source_owner_module: universeForm.source_owner_module.trim(),
      source_type: universeForm.source_type.trim(),
      source_id: universeForm.source_id.trim(),
      source_route: universeForm.source_route.trim() || undefined,
      risk_classification: universeForm.risk_classification,
      regulatory_criticality: universeForm.regulatory_criticality,
      surveillance_interval_days: universeForm.surveillance_interval_days ? Number(universeForm.surveillance_interval_days) : undefined,
      mandatory_surveillance: universeForm.mandatory_surveillance,
      notes: universeForm.notes.trim() || undefined,
    }),
    onSuccess: async (item) => {
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-universe", amoCode] });
      setItemForm((current) => ({ ...current, universe_item_id: item.id }));
      setShowUniverseCreate(false);
    },
  });

  const linksByItem = useMemo(() => new Map((scheduleLinksQuery.data?.items || []).map((link) => [link.programme_item_id, link])), [scheduleLinksQuery.data?.items]);
  const queue = (queueQuery.data?.items || []).filter((item) => !selectedProgrammeId || item.programme_id === selectedProgrammeId);
  const calendarItems = useMemo(() => {
    const months = Array.from({ length: 12 }, () => [] as NonNullable<AuditProgramme["items"]>);
    (selected?.items || []).forEach((item) => {
      const actual = linksByItem.get(item.id)?.next_due_date || item.target_start;
      if (!actual) return;
      const month = Number(actual.slice(5, 7)) - 1;
      if (month >= 0 && month < 12) months[month].push(item);
    });
    return months;
  }, [selected?.items, linksByItem]);

  const error = programmesQuery.error || universeQuery.error || queueQuery.error || detailQuery.error || scheduleLinksQuery.error || createProgrammeMutation.error || transitionMutation.error || amendmentMutation.error || itemMutation.error || universeMutation.error;

  const pickMethodology = (value: AuditProgrammeMethodology) => {
    const method = METHODOLOGIES.find((entry) => entry.value === value);
    setProgrammeForm((current) => ({ ...current, programme_methodology: value }));
    if (method) setItemForm((current) => ({ ...current, driver: method.driver }));
  };

  return (
    <main className="qms-audit-programme qms-audit-programme-flow" aria-label="Audit Programme">
      <header className="qms-audit-programme__header qms-audit-programme-flow__hero">
        <div>
          <span><ClipboardCheck size={15} /> Assurance planning</span>
          <h1>Audit Programme</h1>
          <p>Define why audits are required, decide coverage and target windows, approve the programme, then commit each audit to the shared Quality Planner.</p>
        </div>
        <div className="qms-audit-programme__header-actions">
          <Link className="qms-audit-programme-flow__planner-link" to={`/maintenance/${encodeURIComponent(amoCode)}/quality/calendar`}><CalendarDays size={15} /> Open Quality Planner</Link>
          <label><span>Programme year</span><input type="number" min={2000} max={2200} value={year} onChange={(event) => setYear(Number(event.target.value) || currentYear)} /></label>
          <button type="button" onClick={() => { void programmesQuery.refetch(); void universeQuery.refetch(); void queueQuery.refetch(); }}><RefreshCw size={15} /> Refresh</button>
          {canManage ? <button type="button" className="is-primary" onClick={() => setShowCreate((value) => !value)}><Plus size={15} /> New programme</button> : null}
        </div>
      </header>

      <nav className="qms-audit-programme-flow__steps" aria-label="Audit programme workflow">
        <span className="is-current"><b>1</b><strong>Basis</strong><small>Compliance, performance or risk</small></span>
        <ChevronRight size={16} />
        <span><b>2</b><strong>Coverage</strong><small>What must be audited and why</small></span>
        <ChevronRight size={16} />
        <span><b>3</b><strong>Target calendar</strong><small>Frequency and audit windows</small></span>
        <ChevronRight size={16} />
        <span><b>4</b><strong>Approve</strong><small>Freeze the governed revision</small></span>
        <ChevronRight size={16} />
        <span><b>5</b><strong>Planner & execution</strong><small>People, exact dates and delivery</small></span>
      </nav>

      {error ? <div className="qms-audit-programme__error" role="alert"><AlertTriangle size={16} /> {error instanceof Error ? error.message : "Audit programme data could not be loaded."}</div> : null}

      {showCreate ? (
        <form className="qms-audit-programme__form qms-audit-programme-flow__create" onSubmit={(event) => { event.preventDefault(); createProgrammeMutation.mutate(); }}>
          <header><strong>Create programme revision</strong><small>Choose the primary planning methodology first. It does not replace mandatory regulatory coverage.</small></header>
          <fieldset className="qms-audit-programme-flow__methodologies">
            <legend>Primary planning methodology</legend>
            {METHODOLOGIES.map(({ value, title, description, icon: Icon }) => (
              <label key={value} className={programmeForm.programme_methodology === value ? "is-selected" : ""}>
                <input type="radio" name="programme-methodology" value={value} checked={programmeForm.programme_methodology === value} onChange={() => pickMethodology(value)} />
                <Icon size={18} /><span><strong>{title}</strong><small>{description}</small></span>
              </label>
            ))}
          </fieldset>
          <label className="is-wide"><span>Programme title</span><input required minLength={3} value={programmeForm.title} onChange={(event) => setProgrammeForm((current) => ({ ...current, title: event.target.value }))} /></label>
          <label><span>Programme start</span><input required type="date" value={programmeForm.period_start} onChange={(event) => setProgrammeForm((current) => ({ ...current, period_start: event.target.value }))} /></label>
          <label><span>Programme end</span><input required type="date" value={programmeForm.period_end} onChange={(event) => setProgrammeForm((current) => ({ ...current, period_end: event.target.value }))} /></label>
          <label className="is-wide"><span>Why this methodology?</span><textarea rows={2} value={programmeForm.methodology_rationale} onChange={(event) => setProgrammeForm((current) => ({ ...current, methodology_rationale: event.target.value }))} placeholder="Optional planning rationale, e.g. increased risk following recurring findings or performance deterioration." /></label>
          <label className="is-wide"><span>Programme objectives · one per line</span><textarea rows={3} value={programmeForm.objectives} onChange={(event) => setProgrammeForm((current) => ({ ...current, objectives: event.target.value }))} /></label>
          <label className="is-wide"><span>Governing requirements · one reference per line</span><textarea rows={3} value={programmeForm.regulatory_basis} onChange={(event) => setProgrammeForm((current) => ({ ...current, regulatory_basis: event.target.value }))} placeholder="KCAR / MPM / ISO / IOSA / customer or contractual requirement" /></label>
          <footer><button type="button" onClick={() => setShowCreate(false)}>Cancel</button><button className="is-primary" disabled={createProgrammeMutation.isPending}>Create draft programme</button></footer>
        </form>
      ) : null}

      <div className="qms-audit-programme__workspace qms-audit-programme-flow__workspace">
        <aside className="qms-audit-programme__portfolio">
          <header><strong>Programme revisions</strong><small>{programmes.length} in {year}</small></header>
          {!programmes.length ? <p>No programme exists for {year}.</p> : programmes.map((programme) => (
            <button key={programme.id} type="button" className={programme.id === selectedProgrammeId ? "is-active" : ""} onClick={() => setSelectedId(programme.id)}>
              <span><strong>{programme.title}</strong><small>{programme.programme_ref} · {human(methodologyOf(programme))}</small></span>
              <small>Rev {programme.revision_no}</small><b>{human(programme.status)}</b>
            </button>
          ))}
        </aside>

        <section className="qms-audit-programme__detail">
          {!selectedProgrammeId ? <p>Select or create a programme.</p> : detailQuery.isLoading ? <p>Loading programme…</p> : !selected ? <p>Programme not available.</p> : (
            <>
              <header className="qms-audit-programme__detail-header">
                <div><span>{selected.programme_ref} · Rev {selected.revision_no}</span><h2>{selected.title}</h2><p>{dateLabel(selected.period_start)} → {dateLabel(selected.period_end)}</p></div>
                <span>{human(selected.status)}</span>
              </header>

              <section className="qms-audit-programme-flow__basis" aria-label="Programme planning basis">
                <div className={`is-${selectedMethodology.toLowerCase()}`}>
                  <span>Primary methodology</span><strong>{human(selectedMethodology)} based</strong>
                  <p>{METHODOLOGIES.find((entry) => entry.value === selectedMethodology)?.description}</p>
                  {selected.methodology_rationale ? <small>{selected.methodology_rationale}</small> : null}
                </div>
                <dl>
                  <div><dt>Requirements</dt><dd>{readiness.requirement_count}</dd></div>
                  <div><dt>Mandatory</dt><dd>{readiness.mandatory_requirement_count}</dd></div>
                  <div><dt>High risk</dt><dd>{readiness.high_risk_requirement_count}</dd></div>
                  <div><dt>Needs scheduling</dt><dd>{readiness.unscheduled_requirement_count}</dd></div>
                </dl>
              </section>

              <section className={`qms-audit-programme-flow__readiness ${readiness.ready_for_approval ? "is-ready" : "is-blocked"}`} aria-label="Programme approval readiness">
                <div>{readiness.ready_for_approval ? <CheckCircle2 size={18} /> : <TriangleAlert size={18} />}<span><strong>{readiness.ready_for_approval ? "Ready for approval review" : "Programme setup incomplete"}</strong><small>{readiness.ready_for_approval ? "Coverage has target windows and audit criteria." : `${readiness.blockers.length} item${readiness.blockers.length === 1 ? "" : "s"} must be resolved before approval.`}</small></span></div>
                {!readiness.ready_for_approval ? <ul>{readiness.blockers.slice(0, 5).map((blocker, index) => <li key={`${blocker.code}-${index}`}>{blocker.message}</li>)}</ul> : null}
              </section>

              <section className="qms-audit-programme__requirements qms-audit-programme-flow__coverage">
                <header><div><strong><Target size={15} /> 2. Coverage requirements</strong><small>Each row is one governed audit requirement. The programme method explains why it is prioritised; the subject explains what is audited.</small></div>{canManage && selected.status === "DRAFT" ? <button type="button" onClick={() => setShowRequirement((value) => !value)}><Plus size={14} /> Add coverage</button> : null}</header>
                {showRequirement ? (
                  <form className="qms-audit-programme__form is-embedded" onSubmit={(event) => { event.preventDefault(); itemMutation.mutate(); }}>
                    <label><span>Auditable entity</span><select required value={itemForm.universe_item_id} onChange={(event) => setItemForm((current) => ({ ...current, universe_item_id: event.target.value }))}><option value="">Select entity</option>{(universeQuery.data?.items || []).filter((item) => item.active).map((item) => <option key={item.id} value={item.id}>{item.display_label} · {human(item.entity_type)}</option>)}</select></label>
                    <label><span>Audit subject / coverage type</span><select value={itemForm.audit_type} onChange={(event) => setItemForm((current) => ({ ...current, audit_type: event.target.value }))}>{AUDIT_SUBJECTS.map((value) => <option key={value} value={value}>{human(value)}</option>)}</select></label>
                    <label><span>Primary planning driver</span><select value={itemForm.driver} onChange={(event) => setItemForm((current) => ({ ...current, driver: event.target.value as typeof DRIVERS[number] }))}>{DRIVERS.map((value) => <option key={value} value={value}>{human(value)}</option>)}</select></label>
                    <label><span>Cadence</span><select value={itemForm.recurrence} onChange={(event) => setItemForm((current) => ({ ...current, recurrence: event.target.value }))}>{RECURRENCES.map((value) => <option key={value} value={value}>{human(value)}</option>)}</select></label>
                    <label className="is-wide"><span>Audit title</span><input required minLength={3} value={itemForm.title} onChange={(event) => setItemForm((current) => ({ ...current, title: event.target.value }))} /></label>
                    <label className="is-wide"><span>Purpose / reason for inclusion</span><textarea rows={2} value={itemForm.purpose} onChange={(event) => setItemForm((current) => ({ ...current, purpose: event.target.value }))} /></label>
                    <label className="is-wide"><span>Scope</span><textarea required rows={3} value={itemForm.scope} onChange={(event) => setItemForm((current) => ({ ...current, scope: event.target.value }))} /></label>
                    <label className="is-wide"><span>Audit criteria · one reference per line</span><textarea required rows={3} value={itemForm.criteria} onChange={(event) => setItemForm((current) => ({ ...current, criteria: event.target.value }))} /></label>
                    <label><span>Target window start</span><input required type="date" value={itemForm.target_start} onChange={(event) => setItemForm((current) => ({ ...current, target_start: event.target.value }))} /></label>
                    <label><span>Target window end</span><input required type="date" value={itemForm.target_end} onChange={(event) => setItemForm((current) => ({ ...current, target_end: event.target.value }))} /></label>
                    <label className="is-checkbox"><input type="checkbox" checked={itemForm.mandatory_surveillance} onChange={(event) => setItemForm((current) => ({ ...current, mandatory_surveillance: event.target.checked }))} /><span>Mandatory / minimum surveillance</span></label>
                    <footer><button type="button" onClick={() => setShowRequirement(false)}>Cancel</button><button className="is-primary" disabled={itemMutation.isPending}>Add to programme</button></footer>
                  </form>
                ) : null}
                {!selected.items?.length ? <p className="is-empty">No coverage requirements yet. Add auditable entities and define the required surveillance before submitting the programme for review.</p> : (
                  <div className="qms-audit-programme__table-wrap"><table><thead><tr><th>Audit requirement</th><th>Why</th><th>Target window</th><th>Status</th><th>Next action</th></tr></thead><tbody>{selected.items.map((item) => {
                    const link = linksByItem.get(item.id);
                    const driver = String(item.prioritization_basis?.[0]?.driver || selectedMethodology);
                    return <tr key={item.id}><td><strong>{item.title}</strong><small>{item.auditable_entity?.display_label || "Unlinked entity"} · {human(item.audit_type)}</small></td><td>{human(driver)}<small>{item.mandatory_surveillance ? "Mandatory minimum" : `Risk ${human(item.auditable_entity?.risk_classification || "MEDIUM")}`}</small></td><td>{dateLabel(item.target_start)}<small>to {dateLabel(item.target_end)} · {human(item.recurrence)}</small></td><td><strong>{human(item.state)}</strong>{link?.next_due_date ? <small>Planner: {dateLabel(link.next_due_date)}</small> : null}</td><td>{item.state === "PLANNED" ? <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits/program/${encodeURIComponent(selected.id)}/items/${encodeURIComponent(item.id)}/schedule`}>Schedule <CalendarClock size={14} /></Link> : <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/calendar`}>Open planner <CalendarDays size={14} /></Link>}</td></tr>;
                  })}</tbody></table></div>
                )}
              </section>

              <section className="qms-audit-programme-flow__calendar" aria-label="Audit programme calendar">
                <header><div><strong><CalendarDays size={16} /> 3. Programme calendar</strong><small>Target windows remain governed by the approved programme. Exact dates, people, times and conflicts are committed in the Quality Planner.</small></div><Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/calendar`}>Full planner <ArrowRight size={14} /></Link></header>
                <div className="qms-audit-programme-flow__months">{MONTHS.map((month, index) => <article key={month}><span>{month}</span>{calendarItems[index].length ? calendarItems[index].map((item) => {
                  const schedule = linksByItem.get(item.id);
                  return <Link key={item.id} className={schedule?.schedule_id ? "is-scheduled" : "is-target"} to={schedule?.schedule_id ? `/maintenance/${encodeURIComponent(amoCode)}/quality/calendar` : `/maintenance/${encodeURIComponent(amoCode)}/quality/audits/program/${encodeURIComponent(selected.id)}/items/${encodeURIComponent(item.id)}/schedule`}><strong>{item.title}</strong><small>{schedule?.next_due_date ? `Scheduled ${dateLabel(schedule.next_due_date)}` : `Target ${dateLabel(item.target_start)}`}</small></Link>;
                }) : <small className="is-empty-month">—</small>}</article>)}</div>
              </section>

              <section className="qms-audit-programme-flow__queue" aria-label="Programme scheduling queue">
                <header><div><strong><CalendarClock size={16} /> Needs scheduling</strong><small>Approved or active programme requirements waiting for an authoritative Planner commitment.</small></div></header>
                {!queue.length ? <p>{selected.status === "DRAFT" || selected.status === "UNDER_REVIEW" ? "Scheduling becomes available after programme approval." : "No approved requirements are waiting for scheduling."}</p> : <div>{queue.map((item) => SCHEDULABLE_RECURRENCES.has(item.recurrence) ? <Link key={item.programme_item_id} to={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits/program/${encodeURIComponent(item.programme_id)}/items/${encodeURIComponent(item.programme_item_id)}/schedule`}><span><strong>{item.title}</strong><small>{dateLabel(item.target_start)} → {dateLabel(item.target_end)} · {human(item.recurrence)}</small></span><CalendarClock size={16} /></Link> : <span key={item.programme_item_id}><strong>{item.title}</strong><small>{human(item.recurrence)} requires a governed occurrence trigger.</small></span>)}</div>}
              </section>

              {transitionTargets(selected.status).length || (selected.status !== "DRAFT" && selected.status !== "SUPERSEDED" && canManage) ? (
                <section className="qms-audit-programme__governance qms-audit-programme-flow__approval">
                  <div><strong><ShieldCheck size={15} /> 4. Review and approve</strong><p>Approval freezes this revision. Scheduling happens afterwards in the Planner without changing the approved coverage decision.</p></div>
                  <div className="qms-audit-programme__actions">
                    <input aria-label="Programme transition reason" value={actionReason} onChange={(event) => setActionReason(event.target.value)} placeholder="Decision / amendment reason" />
                    {transitionTargets(selected.status).map((target) => <button key={target} type="button" disabled={!canManage || actionReason.trim().length < 3 || transitionMutation.isPending || (target === "APPROVED" && !readiness.ready_for_approval)} onClick={() => transitionMutation.mutate(target)}>{target === "UNDER_REVIEW" ? "Submit for review" : human(target)} <ArrowRight size={14} /></button>)}
                    {selected.status !== "DRAFT" && selected.status !== "SUPERSEDED" && canManage ? <button type="button" disabled={actionReason.trim().length < 3 || amendmentMutation.isPending} onClick={() => amendmentMutation.mutate()}>Create amendment</button> : null}
                  </div>
                </section>
              ) : null}

              <details className="qms-audit-programme-flow__history">
                <summary>Programme history <small>{selected.events?.length || 0} events</small></summary>
                <div>{[...(selected.events || [])].reverse().map((event) => <article key={event.id}><span><strong>{human(event.event_type)}</strong><small>{new Date(event.created_at).toLocaleString()}</small></span><p>{event.reason}</p></article>)}</div>
              </details>
            </>
          )}
        </section>
      </div>

      <section className="qms-audit-programme__universe qms-audit-programme-flow__universe" aria-labelledby="qms-audit-universe-heading">
        <header><div><span><Library size={14} /> Coverage library</span><h2 id="qms-audit-universe-heading">Audit Universe</h2><p>The auditable entities that can be brought into a programme. This is a library, not the programme itself.</p></div>{canManage ? <button type="button" onClick={() => setShowUniverseCreate((value) => !value)}><Plus size={14} /> Add auditable entity</button> : null}</header>
        {showUniverseCreate ? <form className="qms-audit-programme__form is-embedded" onSubmit={(event) => { event.preventDefault(); universeMutation.mutate(); }}><label><span>Entity type</span><select value={universeForm.entity_type} onChange={(event) => setUniverseForm((current) => ({ ...current, entity_type: event.target.value as AuditUniverseEntityType }))}>{UNIVERSE_TYPES.map((value) => <option key={value} value={value}>{human(value)}</option>)}</select></label><label><span>Display label</span><input required value={universeForm.display_label} onChange={(event) => setUniverseForm((current) => ({ ...current, display_label: event.target.value }))} /></label><label><span>Authoritative source module</span><input required value={universeForm.source_owner_module} onChange={(event) => setUniverseForm((current) => ({ ...current, source_owner_module: event.target.value }))} /></label><label><span>Source record type</span><input required value={universeForm.source_type} onChange={(event) => setUniverseForm((current) => ({ ...current, source_type: event.target.value }))} /></label><label><span>Source record ID</span><input required value={universeForm.source_id} onChange={(event) => setUniverseForm((current) => ({ ...current, source_id: event.target.value }))} /></label><label><span>Source route</span><input value={universeForm.source_route} onChange={(event) => setUniverseForm((current) => ({ ...current, source_route: event.target.value }))} /></label><label><span>Inherent risk</span><select value={universeForm.risk_classification} onChange={(event) => setUniverseForm((current) => ({ ...current, risk_classification: event.target.value as AuditRiskLevel }))}>{RISKS.map((value) => <option key={value} value={value}>{human(value)}</option>)}</select></label><label><span>Regulatory criticality</span><select value={universeForm.regulatory_criticality} onChange={(event) => setUniverseForm((current) => ({ ...current, regulatory_criticality: event.target.value as AuditRiskLevel }))}>{RISKS.map((value) => <option key={value} value={value}>{human(value)}</option>)}</select></label><label><span>Minimum surveillance interval (days)</span><input type="number" min={1} value={universeForm.surveillance_interval_days} onChange={(event) => setUniverseForm((current) => ({ ...current, surveillance_interval_days: event.target.value }))} /></label><label className="is-checkbox"><input type="checkbox" checked={universeForm.mandatory_surveillance} onChange={(event) => setUniverseForm((current) => ({ ...current, mandatory_surveillance: event.target.checked }))} /><span>Mandatory surveillance</span></label><label className="is-wide"><span>Notes</span><textarea rows={2} value={universeForm.notes} onChange={(event) => setUniverseForm((current) => ({ ...current, notes: event.target.value }))} /></label><footer><button type="button" onClick={() => setShowUniverseCreate(false)}>Cancel</button><button className="is-primary" disabled={universeMutation.isPending}>Add entity</button></footer></form> : null}
        <div className="qms-audit-programme-flow__universe-list">{(universeQuery.data?.items || []).map((item) => <article key={item.id}><span>{human(item.entity_type)}</span><strong>{item.display_label}</strong><small>{item.source_owner_module} · {item.source_type}</small><footer><b>{human(item.risk_classification)} risk</b><b>{human(item.regulatory_criticality)} criticality</b>{item.mandatory_surveillance ? <b>Mandatory</b> : null}{item.source_route ? <Link to={item.source_route}>Source</Link> : null}</footer></article>)}</div>
      </section>
    </main>
  );
};

export default QmsAuditProgrammePageV2;
