import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CalendarDays, ClipboardCheck, Plus, RefreshCw, ShieldCheck } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { hasQmsRolePermission } from "../../app/routeGuards";
import {
  addAuditProgrammeItem,
  createAuditProgramme,
  createAuditProgrammeAmendment,
  createAuditUniverseItem,
  getAuditProgramme,
  listAuditProgrammes,
  listAuditUniverse,
  transitionAuditProgramme,
  type AuditProgramme,
  type AuditProgrammeList,
  type AuditProgrammeStatus,
  type AuditRiskLevel,
  type AuditUniverseEntityType,
} from "../../services/qmsAuditProgramme";
import "../../styles/qms-audit-programme.css";

const AUDIT_TYPES = ["INTERNAL", "DEPARTMENTAL", "TECHNICAL", "WORK_PACK", "SUPPLIER", "CONTRACTED_FUNCTION", "FACILITY", "PERSONNEL", "PRODUCT", "PROCESS", "REGULATORY", "SPECIAL", "REACTIVE", "FOLLOW_UP"] as const;
const UNIVERSE_TYPES: AuditUniverseEntityType[] = ["DEPARTMENT", "FACILITY", "STATION", "SUPPLIER", "CONTRACTOR", "PROCESS", "CAPABILITY", "APPROVAL_RATING", "AIRCRAFT_TYPE", "PERSONNEL_GROUP", "OTHER"];
const RISKS: AuditRiskLevel[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

function human(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateLabel(value?: string | null): string {
  if (!value) return "—";
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

const QmsAuditProgrammePage: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const queryClient = useQueryClient();
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showUniverseCreate, setShowUniverseCreate] = useState(false);
  const [showItemCreate, setShowItemCreate] = useState(false);
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
  const programmes = useMemo<AuditProgramme[]>(() => programmesQuery.data?.items ?? [], [programmesQuery.data?.items]);
  const selectedProgrammeId = selectedId || programmes[0]?.id || null;
  const detailQuery = useQuery({
    queryKey: ["qms-audit-programme", amoCode, selectedProgrammeId],
    queryFn: ({ signal }) => getAuditProgramme(amoCode, selectedProgrammeId as string, signal),
    enabled: Boolean(selectedProgrammeId),
    staleTime: 3_000,
  });
  const selected = detailQuery.data;

  const [programmeForm, setProgrammeForm] = useState({
    title: `${currentYear} Quality Audit Programme`, period_start: `${currentYear}-01-01`, period_end: `${currentYear}-12-31`,
    objectives: "Verify continuing conformity and effectiveness of the Quality system.", regulatory_basis: "",
  });
  const [universeForm, setUniverseForm] = useState({
    entity_type: "DEPARTMENT" as AuditUniverseEntityType, display_label: "", source_owner_module: "", source_type: "DEPARTMENT", source_id: "",
    source_route: "", risk_classification: "MEDIUM" as AuditRiskLevel, regulatory_criticality: "MEDIUM" as AuditRiskLevel,
    surveillance_interval_days: "365", mandatory_surveillance: false, notes: "",
  });
  const [itemForm, setItemForm] = useState({
    universe_item_id: "", audit_type: "INTERNAL", title: "", purpose: "", scope: "", criteria: "",
    recurrence: "ANNUAL", mandatory_surveillance: false, target_start: "", target_end: "",
  });

  const invalidateProgramme = async (programmeId?: string) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-programmes", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-programme", amoCode, programmeId || selectedProgrammeId] }),
    ]);
  };

  const createProgrammeMutation = useMutation({
    mutationFn: () => createAuditProgramme(amoCode, {
      programme_year: year, title: programmeForm.title.trim(),
      objectives: programmeForm.objectives.split("\n").map((value) => value.trim()).filter(Boolean),
      regulatory_basis: programmeForm.regulatory_basis.split("\n").map((value) => value.trim()).filter(Boolean),
      period_start: programmeForm.period_start, period_end: programmeForm.period_end,
    }),
    onSuccess: async (programme) => { setSelectedId(programme.id); setShowCreate(false); await invalidateProgramme(programme.id); },
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
    onSuccess: async (programme) => { setSelectedId(programme.id); setActionReason(""); await invalidateProgramme(programme.id); },
  });

  const universeMutation = useMutation({
    mutationFn: () => createAuditUniverseItem(amoCode, {
      entity_type: universeForm.entity_type, display_label: universeForm.display_label.trim(),
      source_owner_module: universeForm.source_owner_module.trim(), source_type: universeForm.source_type.trim(), source_id: universeForm.source_id.trim(),
      source_route: universeForm.source_route.trim() || undefined, risk_classification: universeForm.risk_classification,
      regulatory_criticality: universeForm.regulatory_criticality, surveillance_interval_days: universeForm.surveillance_interval_days ? Number(universeForm.surveillance_interval_days) : undefined,
      mandatory_surveillance: universeForm.mandatory_surveillance, notes: universeForm.notes.trim() || undefined,
    }),
    onSuccess: async (item) => {
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-universe", amoCode] });
      setItemForm((current) => ({ ...current, universe_item_id: item.id })); setShowUniverseCreate(false);
      setUniverseForm((current) => ({ ...current, display_label: "", source_id: "", source_route: "", notes: "" }));
    },
  });

  const itemMutation = useMutation({
    mutationFn: () => addAuditProgrammeItem(amoCode, selectedProgrammeId as string, {
      universe_item_id: itemForm.universe_item_id, audit_type: itemForm.audit_type, title: itemForm.title.trim(),
      purpose: itemForm.purpose.trim() || undefined, scope: itemForm.scope.trim(),
      criteria: itemForm.criteria.split("\n").map((value) => value.trim()).filter(Boolean),
      mandatory_surveillance: itemForm.mandatory_surveillance, recurrence: itemForm.recurrence,
      target_start: itemForm.target_start || undefined, target_end: itemForm.target_end || undefined,
      prioritization_basis: [],
    }),
    onSuccess: async () => {
      setShowItemCreate(false); setItemForm((current) => ({ ...current, title: "", purpose: "", scope: "", criteria: "", target_start: "", target_end: "" }));
      await invalidateProgramme();
    },
  });

  const summary = useMemo(() => programmes.reduce((acc, programme) => {
    acc.requirements += programme.metrics.planned_audit_count;
    acc.completed += programme.metrics.completed_audit_count;
    acc.deferred += programme.metrics.deferred_audit_count;
    acc.followup += programme.metrics.follow_up_audit_count;
    return acc;
  }, { requirements: 0, completed: 0, deferred: 0, followup: 0 }), [programmes]);

  const error = programmesQuery.error || universeQuery.error || detailQuery.error || createProgrammeMutation.error || transitionMutation.error || amendmentMutation.error || universeMutation.error || itemMutation.error;

  return (
    <main className="qms-audit-programme" aria-label="Audit Programme">
      <header className="qms-audit-programme__header">
        <div><span><ClipboardCheck size={15} /> Audit operations</span><h1>Audit Programme</h1><p>Govern the approved surveillance plan, auditable universe and annual coverage without turning recurring schedules into a shadow programme.</p></div>
        <div className="qms-audit-programme__header-actions">
          <label><span>Programme year</span><input type="number" min={2000} max={2200} value={year} onChange={(event) => setYear(Number(event.target.value) || currentYear)} /></label>
          <button type="button" onClick={() => { void programmesQuery.refetch(); void universeQuery.refetch(); }}><RefreshCw size={15} /> Refresh</button>
          {canManage ? <button type="button" className="is-primary" onClick={() => setShowCreate((value) => !value)}><Plus size={15} /> New programme</button> : null}
        </div>
      </header>

      {error ? <div className="qms-audit-programme__error" role="alert"><AlertTriangle size={16} /> {error instanceof Error ? error.message : "Audit programme data could not be loaded."}</div> : null}

      {showCreate ? (
        <form className="qms-audit-programme__form" onSubmit={(event) => { event.preventDefault(); createProgrammeMutation.mutate(); }}>
          <header><strong>Create governed programme revision</strong><small>Starts in DRAFT. Approval and activation are separate attributable transitions.</small></header>
          <label className="is-wide"><span>Title</span><input required minLength={3} value={programmeForm.title} onChange={(event) => setProgrammeForm((current) => ({ ...current, title: event.target.value }))} /></label>
          <label><span>Period start</span><input required type="date" value={programmeForm.period_start} onChange={(event) => setProgrammeForm((current) => ({ ...current, period_start: event.target.value }))} /></label>
          <label><span>Period end</span><input required type="date" value={programmeForm.period_end} onChange={(event) => setProgrammeForm((current) => ({ ...current, period_end: event.target.value }))} /></label>
          <label className="is-wide"><span>Objectives · one per line</span><textarea rows={3} value={programmeForm.objectives} onChange={(event) => setProgrammeForm((current) => ({ ...current, objectives: event.target.value }))} /></label>
          <label className="is-wide"><span>Regulatory / manual basis · one reference per line</span><textarea rows={3} value={programmeForm.regulatory_basis} onChange={(event) => setProgrammeForm((current) => ({ ...current, regulatory_basis: event.target.value }))} /></label>
          <footer><button type="button" onClick={() => setShowCreate(false)}>Cancel</button><button className="is-primary" disabled={createProgrammeMutation.isPending}>Create draft programme</button></footer>
        </form>
      ) : null}

      <section className="qms-audit-programme__scoreboard" aria-label="Programme coverage summary">
        <article><span>Planned audits</span><strong>{summary.requirements}</strong><small>All governed programme requirements</small></article>
        <article><span>Completed</span><strong>{summary.completed}</strong><small>Completed programme items</small></article>
        <article><span>Deferred</span><strong>{summary.deferred}</strong><small>Items with governed deferral state</small></article>
        <article><span>Follow-up</span><strong>{summary.followup}</strong><small>Items requiring follow-up audit</small></article>
      </section>

      <div className="qms-audit-programme__layout">
        <aside className="qms-audit-programme__rail">
          <header><strong>Programme revisions</strong><small>{programmes.length} in {year}</small></header>
          {!programmes.length ? <p>No programme revisions exist for {year}.</p> : programmes.map((programme) => (
            <button key={programme.id} type="button" className={programme.id === selectedProgrammeId ? "is-active" : ""} onClick={() => setSelectedId(programme.id)}>
              <span>{programme.programme_ref}</span><strong>{programme.title}</strong><small>Rev {programme.revision_no} · {human(programme.status)}</small>
            </button>
          ))}
        </aside>

        <section className="qms-audit-programme__detail">
          {!selectedProgrammeId ? <p>Select or create a programme revision.</p> : detailQuery.isLoading ? <p>Loading programme…</p> : !selected ? <p>Programme not available.</p> : (
            <>
              <header className="qms-audit-programme__detail-header"><div><span>{selected.programme_ref} · Rev {selected.revision_no}</span><h2>{selected.title}</h2><small>{dateLabel(selected.period_start)} → {dateLabel(selected.period_end)}</small></div><span className={`is-${selected.status.toLowerCase()}`}>{human(selected.status)}</span></header>
              <div className="qms-audit-programme__facts"><div><span>Status</span><strong>{human(selected.status)}</strong></div><div><span>Planned</span><strong>{selected.metrics.planned_audit_count}</strong></div><div><span>Completed</span><strong>{selected.metrics.completed_audit_count}</strong></div><div><span>Scheduled</span><strong>{selected.metrics.scheduled_audit_count}</strong></div></div>

              <section className="qms-audit-programme__governance"><header><ShieldCheck size={17} /><div><strong>Governance</strong><small>State changes require an attributable reason.</small></div></header><textarea aria-label="Programme transition reason" rows={3} value={actionReason} onChange={(event) => setActionReason(event.target.value)} placeholder="Reason for transition or amendment" />
                <div>{transitionTargets(selected.status).map((target) => <button key={target} type="button" disabled={!canManage || actionReason.trim().length < 3 || transitionMutation.isPending} onClick={() => transitionMutation.mutate(target)}>{target === "UNDER_REVIEW" ? "Submit for review" : human(target)} <ArrowRight size={14} /></button>)}{selected.status !== "DRAFT" && selected.status !== "SUPERSEDED" && canManage ? <button type="button" disabled={actionReason.trim().length < 3 || amendmentMutation.isPending} onClick={() => amendmentMutation.mutate()}>Create amendment</button> : null}</div>
              </section>

              <section className="qms-audit-programme__items"><header><div><strong>Programme requirements</strong><small>{selected.items?.length || 0} governed audit requirements</small></div>{canManage && selected.status === "DRAFT" ? <button type="button" onClick={() => setShowItemCreate((value) => !value)}><Plus size={14} /> Add requirement</button> : null}</header>
                {showItemCreate ? <form onSubmit={(event) => { event.preventDefault(); itemMutation.mutate(); }}><label><span>Auditable universe item</span><select required value={itemForm.universe_item_id} onChange={(event) => setItemForm((current) => ({ ...current, universe_item_id: event.target.value }))}><option value="">Select item</option>{(universeQuery.data?.items || []).filter((item) => item.active).map((item) => <option key={item.id} value={item.id}>{item.display_label} · {human(item.entity_type)}</option>)}</select></label><label><span>Audit type</span><select value={itemForm.audit_type} onChange={(event) => setItemForm((current) => ({ ...current, audit_type: event.target.value }))}>{AUDIT_TYPES.map((value) => <option key={value} value={value}>{human(value)}</option>)}</select></label><label className="is-wide"><span>Title</span><input required minLength={3} value={itemForm.title} onChange={(event) => setItemForm((current) => ({ ...current, title: event.target.value }))} /></label><label className="is-wide"><span>Scope</span><textarea required rows={3} value={itemForm.scope} onChange={(event) => setItemForm((current) => ({ ...current, scope: event.target.value }))} /></label><label className="is-wide"><span>Criteria · one per line</span><textarea rows={3} value={itemForm.criteria} onChange={(event) => setItemForm((current) => ({ ...current, criteria: event.target.value }))} /></label><label><span>Target start</span><input type="date" value={itemForm.target_start} onChange={(event) => setItemForm((current) => ({ ...current, target_start: event.target.value }))} /></label><label><span>Target end</span><input type="date" value={itemForm.target_end} onChange={(event) => setItemForm((current) => ({ ...current, target_end: event.target.value }))} /></label><label><span>Recurrence</span><input value={itemForm.recurrence} onChange={(event) => setItemForm((current) => ({ ...current, recurrence: event.target.value }))} /></label><label><span><input type="checkbox" checked={itemForm.mandatory_surveillance} onChange={(event) => setItemForm((current) => ({ ...current, mandatory_surveillance: event.target.checked }))} /> Mandatory surveillance</span></label><footer><button type="button" onClick={() => setShowItemCreate(false)}>Cancel</button><button className="is-primary" disabled={itemMutation.isPending}>Add requirement</button></footer></form> : null}
                {!selected.items?.length ? <p>No audit requirements have been added to this programme revision.</p> : <div className="qms-audit-programme__item-list">{selected.items.map((item) => <article key={item.id}><div><span>{human(item.audit_type)} · {human(item.state)}</span><strong>{item.title}</strong><small>{item.auditable_entity?.display_label || "Unlinked auditable entity"}</small><p>{item.scope}</p></div><div><span>{dateLabel(item.target_start)}</span><span>{dateLabel(item.target_end)}</span><strong>{human(item.auditable_entity?.risk_classification || "MEDIUM")}</strong></div><Link to={`/maintenance/${encodeURIComponent(amoCode)}/qms/audits/planner?programmeItemId=${encodeURIComponent(item.id)}`}>Schedule <CalendarDays size={14} /></Link></article>)}</div>}
              </section>
            </>
          )}
        </section>
      </div>

      <section className="qms-audit-programme__universe" aria-labelledby="qms-audit-universe-heading"><header><div><h2 id="qms-audit-universe-heading">Audit Universe</h2><small>Stable auditable-entity keys consumed by the programme; this is not a second roster.</small></div>{canManage ? <button type="button" onClick={() => setShowUniverseCreate((value) => !value)}><Plus size={14} /> Add universe item</button> : null}</header>{showUniverseCreate ? <form onSubmit={(event) => { event.preventDefault(); universeMutation.mutate(); }}><label><span>Entity type</span><select value={universeForm.entity_type} onChange={(event) => setUniverseForm((current) => ({ ...current, entity_type: event.target.value as AuditUniverseEntityType }))}>{UNIVERSE_TYPES.map((value) => <option key={value} value={value}>{human(value)}</option>)}</select></label><label><span>Display label</span><input required minLength={2} value={universeForm.display_label} onChange={(event) => setUniverseForm((current) => ({ ...current, display_label: event.target.value }))} /></label><label><span>Source module</span><input required value={universeForm.source_owner_module} onChange={(event) => setUniverseForm((current) => ({ ...current, source_owner_module: event.target.value }))} /></label><label><span>Source type</span><input required value={universeForm.source_type} onChange={(event) => setUniverseForm((current) => ({ ...current, source_type: event.target.value }))} /></label><label><span>Source ID</span><input required value={universeForm.source_id} onChange={(event) => setUniverseForm((current) => ({ ...current, source_id: event.target.value }))} /></label><label><span>Source route</span><input value={universeForm.source_route} onChange={(event) => setUniverseForm((current) => ({ ...current, source_route: event.target.value }))} /></label><label><span>Risk</span><select value={universeForm.risk_classification} onChange={(event) => setUniverseForm((current) => ({ ...current, risk_classification: event.target.value as AuditRiskLevel }))}>{RISKS.map((value) => <option key={value} value={value}>{human(value)}</option>)}</select></label><label><span>Regulatory criticality</span><select value={universeForm.regulatory_criticality} onChange={(event) => setUniverseForm((current) => ({ ...current, regulatory_criticality: event.target.value as AuditRiskLevel }))}>{RISKS.map((value) => <option key={value} value={value}>{human(value)}</option>)}</select></label><label><span>Surveillance interval (days)</span><input type="number" min={1} value={universeForm.surveillance_interval_days} onChange={(event) => setUniverseForm((current) => ({ ...current, surveillance_interval_days: event.target.value }))} /></label><label><span><input type="checkbox" checked={universeForm.mandatory_surveillance} onChange={(event) => setUniverseForm((current) => ({ ...current, mandatory_surveillance: event.target.checked }))} /> Mandatory surveillance</span></label><label className="is-wide"><span>Notes</span><textarea rows={3} value={universeForm.notes} onChange={(event) => setUniverseForm((current) => ({ ...current, notes: event.target.value }))} /></label><footer><button type="button" onClick={() => setShowUniverseCreate(false)}>Cancel</button><button className="is-primary" disabled={universeMutation.isPending}>Add universe item</button></footer></form> : null}<div className="qms-audit-programme__universe-grid">{(universeQuery.data?.items || []).map((item) => <article key={item.id}><span>{human(item.entity_type)}</span><strong>{item.display_label}</strong><small>{item.source_owner_module} · {item.source_type}:{item.source_id}</small><div><em>{human(item.risk_classification)} risk</em><em>{human(item.regulatory_criticality)} criticality</em>{item.mandatory_surveillance ? <em>Mandatory</em> : null}</div></article>)}</div></section>
    </main>
  );
};

export default QmsAuditProgrammePage;