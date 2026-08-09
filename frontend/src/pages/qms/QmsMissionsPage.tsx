import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  FolderKanban,
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
} from "../../services/qmsMissions";
import "../../styles/qms-missions.css";

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

const MissionRow: React.FC<{ mission: QmsMission; onOpen: () => void }> = ({ mission, onOpen }) => {
  const hard = mission.readiness.hard_gates;
  const blockers = mission.readiness.blocking_gates.length;
  return (
    <button type="button" className="qms-missions__row" onClick={onOpen}>
      <span className="qms-missions__row-ref"><strong>{mission.mission_ref}</strong><small>{humanise(mission.mission_type)}</small></span>
      <span><strong>{mission.title}</strong><small>{mission.description || "No description supplied."}</small></span>
      <span><strong>{humanise(mission.status)}</strong><small>{dateLabel(mission.target_date)}</small></span>
      <span className={`qms-missions__tone is-${riskTone(mission.risk_level)}`}>{humanise(mission.risk_level)}</span>
      <span><strong>{hard.passed}/{hard.total}</strong><small>{blockers ? `${blockers} hard gate${blockers === 1 ? "" : "s"} open` : "Hard gates satisfied"}</small></span>
      <ArrowRight size={16} aria-hidden="true" />
    </button>
  );
};

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

const QmsMissionsPage: React.FC<{ amoCode: string }> = ({ amoCode }) => {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [statusFilter, setStatusFilter] = useState<"" | QmsMissionStatus>("");
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [scopeLabel, setScopeLabel] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [riskLevel, setRiskLevel] = useState<QmsMissionRisk>("MEDIUM");
  const canManage = hasQmsRolePermission("qms.change.manage");
  const selectedMissionId = searchParams.get("missionId");

  const listQuery = useQuery({
    queryKey: ["qms-missions", amoCode, statusFilter],
    queryFn: ({ signal }) => listQmsMissions(amoCode, { status: statusFilter || undefined, limit: 25 }, signal),
    staleTime: 10_000,
  });

  const createMutation = useMutation({
    mutationFn: (payload: QmsMissionCreate) => createQmsMission(amoCode, payload),
    onSuccess: async (mission) => {
      await queryClient.invalidateQueries({ queryKey: ["qms-missions", amoCode] });
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
      mission_type: "CAPABILITY_ADDITION",
      title: title.trim(),
      description: description.trim() || undefined,
      scope: scopeLabel.trim() ? { capability: scopeLabel.trim() } : {},
      risk_level: riskLevel,
      target_date: targetDate || undefined,
    });
  };

  return (
    <main className="qms-missions" aria-label="Quality Missions">
      <header className="qms-missions__header">
        <div><span><FolderKanban size={15} /> Controlled change & capability projects</span><h1>Missions</h1><p>Coordinate cross-department Quality projects through explicit readiness evidence and human approval gates.</p></div>
        <div>
          <button type="button" onClick={() => void listQuery.refetch()} disabled={listQuery.isFetching}><RefreshCw size={15} className={listQuery.isFetching ? "is-spinning" : ""} /> Refresh</button>
          {canManage ? <button type="button" className="is-primary" onClick={() => setShowCreate((value) => !value)}><Plus size={15} /> New capability mission</button> : null}
        </div>
      </header>

      {showCreate ? (
        <form className="qms-missions__create" onSubmit={submitCreate}>
          <header><div><strong>Aircraft / capability inclusion</strong><small>The first governed Mission template seeds 11 hard readiness gates. Nothing is marked compliant automatically.</small></div><button type="button" onClick={() => setShowCreate(false)}>Cancel</button></header>
          <div>
            <label><span>Mission title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required minLength={3} placeholder="DHC-8-400 capability inclusion" /></label>
            <label><span>Capability / scope</span><input value={scopeLabel} onChange={(event) => setScopeLabel(event.target.value)} placeholder="DHC-8-400 · Airframe · Line + Base" /></label>
            <label><span>Target date</span><input type="date" value={targetDate} onChange={(event) => setTargetDate(event.target.value)} /></label>
            <label><span>Initial risk</span><select value={riskLevel} onChange={(event) => setRiskLevel(event.target.value as QmsMissionRisk)}><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label>
            <label className="is-wide"><span>Description</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} placeholder="What capability is being introduced and why?" /></label>
          </div>
          {createMutation.error ? <p className="qms-missions__create-error">{createMutation.error instanceof Error ? createMutation.error.message : "Mission could not be created."}</p> : null}
          <footer><small>Accountable Executive assignment and source-system evidence remain explicit governed steps.</small><button type="submit" className="is-primary" disabled={createMutation.isPending || title.trim().length < 3}>{createMutation.isPending ? "Creating…" : "Create Mission"}</button></footer>
        </form>
      ) : null}

      <section className="qms-missions__metrics" aria-label="Mission portfolio summary">
        <article><span>Visible missions</span><strong>{listQuery.data?.total ?? 0}</strong><small>server-bounded portfolio records</small></article>
        <article><span>Active in this page</span><strong>{totals.active}</strong><small>not complete or cancelled</small></article>
        <article className={totals.blocked ? "is-attention" : ""}><span>Blocked / failed</span><strong>{totals.blocked}</strong><small>missions with failed hard gates</small></article>
        <article><span>Decision-ready</span><strong>{totals.gateReview}</strong><small>gate review or ready for approval</small></article>
      </section>

      <section className="qms-missions__portfolio">
        <header><div><strong>Mission portfolio</strong><small>Readiness is expressed as passed hard gates, never as a regulatory compliance percentage.</small></div><label><span>Status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as "" | QmsMissionStatus)}>{ACTIVE_STATUSES.map((option) => <option key={option.value || "all"} value={option.value}>{option.label}</option>)}</select></label></header>
        <div className="qms-missions__row qms-missions__row-head" aria-hidden="true"><span>Reference</span><span>Mission</span><span>Status / target</span><span>Risk</span><span>Hard gates</span><span /></div>
        {listQuery.isLoading && !listQuery.data ? <div className="qms-missions__state"><RefreshCw size={18} className="is-spinning" /> Loading Mission portfolio…</div> : null}
        {listQuery.error ? <div className="qms-missions__state is-error"><AlertTriangle size={18} /><span>{listQuery.error instanceof Error ? listQuery.error.message : "Mission portfolio could not be loaded."}</span><button type="button" onClick={() => void listQuery.refetch()}>Retry</button></div> : null}
        {!listQuery.isLoading && !listQuery.error && missions.length === 0 ? <div className="qms-missions__state"><ShieldCheck size={18} /><span>No Mission matches the current filter. Existing operational registers remain authoritative; create a Mission only for governed cross-department change.</span></div> : null}
        {missions.map((mission) => <MissionRow key={mission.id} mission={mission} onOpen={() => openMission(mission.id)} />)}
        {listQuery.data ? <footer><span>{missions.length ? `Showing ${missions.length} of ${listQuery.data.total}` : "No rows"}</span><span>{listQuery.data.has_more ? "More records are available through bounded pagination." : "End of current result set."}</span></footer> : null}
      </section>
    </main>
  );
};

export default QmsMissionsPage;
