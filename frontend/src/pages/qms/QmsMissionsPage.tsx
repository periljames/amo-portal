import Pagination from "../../components/shared/Pagination";
import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  Plus,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { hasQmsRolePermission } from "../../app/routeGuards";
import {
  createQmsMission,
  getQmsMission,
  listQmsMissions,
  type QmsMission,
  type QmsMissionCreate,
  type QmsMissionGate,
  type QmsMissionRisk,
  type QmsMissionStatus,
  type QmsMissionType,
} from "../../services/qmsMissions";
import "../../styles/qms/missions.css";
import QmsWorkspaceGrid from "./components/QmsWorkspaceGrid";
import QmsMissionActions from "./missions/QmsMissionActions";

const ACTIVE_STATUSES: Array<{ value: "" | QmsMissionStatus; label: string }> = [
  { value: "", label: "All missions" },
  { value: "PLANNING", label: "Planning" },
  { value: "IN_PROGRESS", label: "In progress" },
  { value: "GATE_REVIEW", label: "Gate review" },
  { value: "READY_FOR_APPROVAL", label: "Ready for approval" },
  { value: "APPROVED", label: "Approved" },
  { value: "SUBMITTED_TO_AUTHORITY", label: "With authority" },
  { value: "COMPLETE", label: "Complete" },
];

function humanise(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateLabel(value: string | null | undefined): string {
  if (!value) return "No target date";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function riskTone(value: QmsMissionRisk): string {
  if (value === "CRITICAL" || value === "HIGH") return "danger";
  if (value === "MEDIUM") return "warning";
  return "positive";
}

function gateIcon(gate: QmsMissionGate): React.ReactNode {
  if (gate.status === "PASS") return <CheckCircle2 size={16} aria-hidden="true" />;
  if (gate.status === "FAIL" || gate.status === "BLOCKED") return <XCircle size={16} aria-hidden="true" />;
  return <CircleDashed size={16} aria-hidden="true" />;
}

function sourceLabel(gate: QmsMissionGate): string {
  if (gate.source_id && gate.evidence_status === "VERIFIED") return `${gate.source_type || "Source"} · verified`;
  if (gate.source_id) return `${gate.source_type || "Source"} · ${humanise(gate.evidence_status)}`;
  return gate.source_owner_module ? `Awaiting ${humanise(gate.source_owner_module)}` : "Evidence not linked";
}

const MissionDetail: React.FC<{ amoCode: string; missionId: string; onBack: () => void }> = ({ amoCode, missionId, onBack }) => {
  const detailQuery = useQuery({
    queryKey: ["qms-mission", amoCode, missionId],
    queryFn: ({ signal }) => getQmsMission(amoCode, missionId, signal),
    staleTime: 5_000,
  });
  const mission = detailQuery.data;

  if (detailQuery.isLoading && !mission) {
    return <div className="qms-missions__state"><RefreshCw size={18} className="is-spinning" /> Loading Mission…</div>;
  }
  if (detailQuery.error || !mission) {
    return (
      <div className="qms-missions__state is-error">
        <AlertTriangle size={18} />
        <span>{detailQuery.error instanceof Error ? detailQuery.error.message : "Mission could not be loaded."}</span>
        <button type="button" onClick={onBack}>Back to portfolio</button>
      </div>
    );
  }

  const readiness = mission.readiness;
  const hard = readiness.hard_gates;
  return (
    <section className="qms-mission-detail" aria-label={`${mission.mission_ref} ${mission.title}`}>
      <header className="qms-mission-detail__header">
        <button type="button" className="qms-mission-detail__back" onClick={onBack}><ArrowLeft size={15} /> Missions</button>
        <div className="qms-mission-detail__title">
          <div>
            <span>{mission.mission_ref} · {humanise(mission.mission_type)}</span>
            <h1>{mission.title}</h1>
            <p>{mission.description || "No mission description has been recorded."}</p>
          </div>
          <div className="qms-mission-detail__badges">
            <span>{humanise(mission.status)}</span>
            <span className={`is-${riskTone(mission.risk_level)}`}>{humanise(mission.risk_level)} risk</span>
          </div>
        </div>
      </header>

      <div className="qms-mission-detail__summary">
        <article><span>Hard gates</span><strong>{hard.passed}/{hard.total}</strong><small>All must pass before Quality self-evaluation.</small></article>
        <article><span>Blocking gates</span><strong>{readiness.blocking_gates.length}</strong><small>Hard dependencies still preventing approval.</small></article>
        <article><span>Target date</span><strong>{dateLabel(mission.target_date)}</strong><small>Planning target, not an approval claim.</small></article>
        <article><span>Accountable Executive</span><strong>{mission.sponsor_user_id ? "Assigned" : "Not assigned"}</strong><small>An attributable sponsor is required before executive approval.</small></article>
      </div>

      <section className="qms-mission-detail__gates">
        <header>
          <div><ShieldCheck size={17} /><span><strong>Readiness gates</strong><small>Evidence pointers reference authoritative source modules; this Mission does not duplicate their records.</small></span></div>
          <span className={readiness.ready_for_quality_self_evaluation ? "is-ready" : ""}>
            {readiness.ready_for_quality_self_evaluation ? "Ready for Quality self-evaluation" : "Hard gates remain open"}
          </span>
        </header>
        <div className="qms-mission-detail__gate-head" aria-hidden="true">
          <span>Gate</span><span>State</span><span>Evidence source</span><span>Requirement</span><span>Action</span>
        </div>
        {(mission.gates || []).map((gate) => (
          <div key={gate.id} className={`qms-mission-detail__gate is-${gate.status.toLowerCase()}`}>
            <span className="qms-mission-detail__gate-title">{gateIcon(gate)}<span><strong>{gate.title}</strong><small>{gate.category} · {gate.gate_type}</small></span></span>
            <span><strong>{humanise(gate.status)}</strong><small>{gate.blocking_reason || humanise(gate.evidence_status)}</small></span>
            <span><strong>{sourceLabel(gate)}</strong><small>{gate.source_id || gate.source_type || "No source reference"}</small></span>
            <span><strong>{gate.requirement_ref || "Requirement mapping pending"}</strong><small>{gate.source_owner_module ? `Owner: ${humanise(gate.source_owner_module)}` : "Owner not assigned"}</small></span>
            <span>{gate.source_route ? <Link to={gate.source_route}>Open source <ArrowRight size={13} /></Link> : <small>Source handoff pending</small>}</span>
          </div>
        ))}
      </section>

      <QmsMissionActions key={`${mission.id}:${mission.updated_at}`} amoCode={amoCode} mission={mission} />
      <div className="qms-mission-detail__lower-grid">
        <section>
          <header><strong>Decision chain</strong><small>Decisions are immutable, human-attributed records.</small></header>
          {mission.decisions?.length ? mission.decisions.map((decision) => (
            <article key={decision.id}>
              <span><strong>{humanise(decision.decision_type)}</strong><small>{humanise(decision.status)}</small></span>
              <p>{decision.rationale}</p>
              <small>{new Date(decision.decided_at).toLocaleString()}</small>
            </article>
          )) : <p className="qms-mission-detail__empty">No approval decision has been recorded.</p>}
        </section>
        <section>
          <header><strong>Mission scope</strong><small>Structured request context carried with the assurance case.</small></header>
          {Object.keys(mission.scope || {}).length ? (
            <dl>{Object.entries(mission.scope).map(([key, value]) => <React.Fragment key={key}><dt>{humanise(key)}</dt><dd>{String(value ?? "—")}</dd></React.Fragment>)}</dl>
          ) : <p className="qms-mission-detail__empty">No structured scope fields have been recorded.</p>}
        </section>
      </div>
    </section>
  );
};

const CHANGE_TYPES: Array<{ value: QmsMissionType; label: string }> = [
  { value: "CAPABILITY_ADDITION", label: "New capability" },
  { value: "CAPABILITY_CHANGE", label: "Capability change" },
  { value: "LINE_STATION", label: "Line station / additional location" },
  { value: "PROCEDURE_CHANGE", label: "MOPM / procedure change" },
  { value: "REGULATORY_TRANSITION", label: "Regulatory / organization change" },
];

const QmsMissionsPage: React.FC<{ amoCode: string; initialCreate?: boolean; changeControl?: boolean }> = ({ amoCode, initialCreate = false, changeControl = false }) => {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [statusFilter, setStatusFilter] = useState<"" | QmsMissionStatus>("");
  const [offset, setOffset] = useState(0);
  const [showCreate, setShowCreate] = useState(initialCreate);
  const [missionType, setMissionType] = useState<QmsMissionType>(changeControl ? "PROCEDURE_CHANGE" : "CAPABILITY_ADDITION");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [scopeLabel, setScopeLabel] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [riskLevel, setRiskLevel] = useState<QmsMissionRisk>("MEDIUM");
  const canManage = hasQmsRolePermission("qms.change.manage");
  const selectedMissionId = searchParams.get("missionId");

  const listQuery = useQuery({
    queryKey: ["qms-missions", amoCode.trim().toLowerCase(), statusFilter, offset],
    queryFn: ({ signal }) => listQmsMissions(amoCode, { status: statusFilter || undefined, limit: 25, offset }, signal),
    staleTime: 10_000,
    enabled: !selectedMissionId,
  });

  const createMutation = useMutation({
    mutationFn: (payload: QmsMissionCreate) => createQmsMission(amoCode, payload),
    onSuccess: async (mission) => {
      await queryClient.invalidateQueries({ queryKey: ["qms-missions", amoCode.trim().toLowerCase()] });
      setShowCreate(false);
      setTitle("");
      setDescription("");
      setScopeLabel("");
      setTargetDate("");
      setRiskLevel("MEDIUM");
      const next = new URLSearchParams(searchParams);
      next.set("workspace", "missions");
      next.set("missionId", mission.id);
      setSearchParams(next);
    },
  });

  const openMission = (missionId: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("workspace", "missions");
    next.set("missionId", missionId);
    setSearchParams(next);
  };
  const backToPortfolio = () => {
    const next = new URLSearchParams(searchParams);
    next.set("workspace", "missions");
    next.delete("missionId");
    setSearchParams(next);
  };

  if (selectedMissionId) return <MissionDetail amoCode={amoCode} missionId={selectedMissionId} onBack={backToPortfolio} />;

  const missions = listQuery.data?.items || [];
  const totals = {
    active: missions.filter((mission) => !["COMPLETE", "CANCELLED"].includes(mission.status)).length,
    blocked: missions.filter((mission) => mission.readiness.blocking_gates.some((gate) => gate.status === "FAIL" || gate.status === "BLOCKED")).length,
    gateReview: missions.filter((mission) => mission.status === "GATE_REVIEW" || mission.status === "READY_FOR_APPROVAL").length,
  };

  const submitCreate = (event: React.FormEvent) => {
    event.preventDefault();
    createMutation.mutate({
      mission_type: missionType,
      title: title.trim(),
      description: description.trim() || undefined,
      scope: { affected_scope: scopeLabel.trim() },
      regulatory_basis: [missionType === "CAPABILITY_ADDITION" ? "MOPM 1.8; capability self-evaluation" : "MOPM 1.9; 1.10"],
      risk_level: riskLevel,
      target_date: targetDate || undefined,
    });
  };

  return (
    <main className="qms-missions" aria-label="Quality Missions">
      <header className="qms-missions__header">
        <div><h1>{changeControl ? "Change Control" : "Change & capability projects"}</h1></div>
        <div>
          <button type="button" onClick={() => void listQuery.refetch()} disabled={listQuery.isFetching}><RefreshCw size={15} className={listQuery.isFetching ? "is-spinning" : ""} /> Refresh</button>
          {canManage ? <button type="button" className="is-primary" onClick={() => setShowCreate((value) => !value)}><Plus size={15} /> New controlled change</button> : null}
        </div>
      </header>

      {showCreate ? (
        <form className="qms-missions__create" onSubmit={submitCreate}>
          <header><strong>New controlled change</strong><button type="button" onClick={() => setShowCreate(false)}>Cancel</button></header>
          <div>
            <label><span>Change type</span><select value={missionType} onChange={event => setMissionType(event.target.value as QmsMissionType)}>{CHANGE_TYPES.map(type => <option key={type.value} value={type.value}>{type.label}</option>)}</select></label>
            <label><span>Change title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required minLength={3} maxLength={255} /></label>
            <label><span>Affected capability, location or procedure</span><input required minLength={3} maxLength={500} value={scopeLabel} onChange={(event) => setScopeLabel(event.target.value)} /></label>
            <label><span>Target date</span><input type="date" value={targetDate} onChange={(event) => setTargetDate(event.target.value)} /></label>
            <label><span>Initial risk</span><select value={riskLevel} onChange={(event) => setRiskLevel(event.target.value as QmsMissionRisk)}><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label>
            <label className="is-wide"><span>Proposed change and reason</span><textarea required minLength={10} maxLength={4000} value={description} onChange={(event) => setDescription(event.target.value)} rows={3} /></label>
          </div>
          {createMutation.error ? <p className="qms-missions__create-error">{createMutation.error instanceof Error ? createMutation.error.message : "Mission could not be created."}</p> : null}
          <footer><small>{missionType === "CAPABILITY_ADDITION" ? "11 capability readiness gates" : "5 MOPM change readiness gates"} · Quality, Executive and Authority decisions remain separate.</small><button type="submit" className="is-primary" disabled={createMutation.isPending || title.trim().length < 3 || scopeLabel.trim().length < 3 || description.trim().length < 10}>{createMutation.isPending ? "Creating…" : "Create controlled change"}</button></footer>
        </form>
      ) : null}

      {!showCreate ? <div className="qms-missions__counts" aria-label="Mission portfolio summary"><span>{listQuery.data?.total ?? 0} projects</span><span>{totals.active} active on this page</span><span>{totals.blocked} blocked</span><span>{totals.gateReview} awaiting decisions</span></div> : null}

      {!showCreate ? <section className="qms-missions__portfolio">
        <header><strong>Controlled projects</strong><label><span>Status</span><select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as "" | QmsMissionStatus); setOffset(0); }}>{ACTIVE_STATUSES.map((option) => <option key={option.value || "all"} value={option.value}>{option.label}</option>)}</select></label></header>
        {listQuery.error ? <p role="alert">{listQuery.error.message}</p> : null}
        <QmsWorkspaceGrid<QmsMission> rowData={missions} loading={listQuery.isLoading} getRowId={({ data }) => data.id} onRowDoubleClicked={({ data }) => { if (data) openMission(data.id); }} columnDefs={[
          { field: "mission_ref", headerName: "Reference" },
          { field: "title", headerName: "Project", minWidth: 260, flex: 2 },
          { field: "status", headerName: "Stage", valueFormatter: ({ value }) => humanise(value) },
          { field: "target_date", headerName: "Target", valueFormatter: ({ value }) => dateLabel(value) },
          { field: "risk_level", headerName: "Risk" },
          { headerName: "Open hard gates", valueGetter: ({ data }) => data ? data.readiness.hard_gates.total - data.readiness.hard_gates.passed : 0 },
          { headerName: "Action", filter: false, sortable: false, cellRenderer: ({ data }: { data?: QmsMission }) => data ? <button type="button" onClick={() => openMission(data.id)}>Manage project</button> : null },
        ]} />
        <Pagination label="Projects" page={Math.floor(offset/25)+1} pageSize={25} total={listQuery.data?.total} visibleCount={listQuery.data?.items?.length || 0} hasNext={Boolean(listQuery.data?.has_more)} busy={listQuery.isFetching} onPageChange={value=>setOffset((value-1)*25)} />
      </section> : null}
    </main>
  );
};

export default QmsMissionsPage;
