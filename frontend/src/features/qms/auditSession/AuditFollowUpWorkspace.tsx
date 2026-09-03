import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clock3, ExternalLink, RefreshCw, RotateCcw, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { apiRequest } from "../../../services/apiClient";
import {
  getAuditClosureState,
  recordAuditFollowUpComplete,
  reopenAuditFollowUp,
} from "../../../services/qmsAuditCloseout";
import { getCarControlLoop } from "../../../services/qmsCarControlLoop";
import { resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";
import { AuditStageLoadError } from "./AuditStageLoadError";
import { auditSessionPath } from "./auditSessionRoutes";

type Props = { amoCode: string; auditKey: string };

type AuditCar = {
  id: string;
  car_number: string;
  title: string;
  summary: string;
  status: string;
  priority: string;
  due_date: string | null;
  target_closure_date: string | null;
  closed_at: string | null;
  escalated_at: string | null;
  assigned_to_user_id: string | null;
  finding_id: string | null;
  audit_id?: string | null;
  finding_ref?: string | null;
  days_out?: number | null;
  days_remaining_past?: number | null;
};

type AuditCarRegister = { items: AuditCar[]; total: number; limit: number; offset: number };

function listAuditCars(auditId: string, signal?: AbortSignal) {
  const params = new URLSearchParams({ audit_id: auditId, limit: "200", offset: "0" });
  return apiRequest<AuditCarRegister>(`/quality/cars/register?${params.toString()}`, {
    timeoutMs: 15_000,
    cacheTtlMs: 2_000,
    signal,
  });
}

function carIsClosed(car: AuditCar): boolean {
  return Boolean(car.closed_at) || ["CLOSED", "VERIFIED", "CANCELLED"].includes(car.status.toUpperCase());
}

function carIsOverdue(car: AuditCar): boolean {
  if (carIsClosed(car)) return false;
  if (typeof car.days_remaining_past === "number" && car.days_remaining_past > 0) return true;
  const controllingDate = car.target_closure_date || car.due_date;
  return Boolean(controllingDate && new Date(`${controllingDate}T23:59:59`).getTime() < Date.now());
}

const AuditFollowUpWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [selectedCarId, setSelectedCarId] = useState<string | null>(null);
  const [completionReason, setCompletionReason] = useState("All governed audit follow-up obligations have satisfied their closure gates.");
  const [localError, setLocalError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: ["qms-follow-up-audit-resolve", amoCode, auditKey],
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const carsQuery = useQuery({
    queryKey: ["qms-audit-cars", amoCode, auditId],
    queryFn: ({ signal }) => listAuditCars(auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const closureQuery = useQuery({
    queryKey: ["qms-audit-closure-state", amoCode, auditId],
    queryFn: ({ signal }) => getAuditClosureState(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });

  const cars = useMemo(() => carsQuery.data?.items || [], [carsQuery.data?.items]);
  const effectiveSelectedCarId = selectedCarId && cars.some((row) => row.id === selectedCarId)
    ? selectedCarId
    : cars.find((row) => !carIsClosed(row))?.id || cars[0]?.id || null;
  const selectedCar = cars.find((row) => row.id === effectiveSelectedCarId) || null;
  const selectedControlQuery = useQuery({
    queryKey: ["qms-car-control-loop", amoCode, effectiveSelectedCarId],
    queryFn: ({ signal }) => getCarControlLoop(amoCode, effectiveSelectedCarId!, signal),
    enabled: Boolean(effectiveSelectedCarId),
    staleTime: 2_000,
  });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-cars", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-closure-state", amoCode, auditId] }),
      effectiveSelectedCarId ? queryClient.invalidateQueries({ queryKey: ["qms-car-control-loop", amoCode, effectiveSelectedCarId] }) : Promise.resolve(),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
    ]);
  };

  const completeMutation = useMutation({
    mutationFn: () => recordAuditFollowUpComplete(amoCode, auditId, completionReason.trim()),
    onSuccess: async () => {
      setLocalError(null);
      setNotice("Assurance follow-up completed. Archive eligibility is now controlled by the authoritative session and retention gates.");
      await refresh();
    },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Follow-up could not be completed."),
  });
  const reopenMutation = useMutation({
    mutationFn: () => reopenAuditFollowUp(amoCode, auditId, completionReason.trim()),
    onSuccess: async () => {
      setLocalError(null);
      setNotice("Follow-up reopened with an attributable lifecycle event.");
      await refresh();
    },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Follow-up could not be reopened."),
  });

  const openCars = cars.filter((row) => !carIsClosed(row));
  const overdueCars = openCars.filter(carIsOverdue);
  const escalatedCars = openCars.filter((row) => Boolean(row.escalated_at));
  const closure = closureQuery.data;
  const selectedControl = selectedControlQuery.data;
  const loadError = auditQuery.error || carsQuery.error || closureQuery.error;

  if (auditQuery.isLoading || carsQuery.isLoading || closureQuery.isLoading) return <section className="qms-occurrence-stage qms-occurrence-stage--loading">Loading audit follow-up…</section>;
  if (loadError || !auditQuery.data || !closure) {
    return (
      <AuditStageLoadError
        className="qms-occurrence-stage qms-occurrence-stage--error"
        title="Follow-up workspace unavailable"
        detail={loadError instanceof Error ? loadError.message : null}
        onRetry={() => {
          void auditQuery.refetch();
          void carsQuery.refetch();
          void closureQuery.refetch();
        }}
        exitHref={auditSessionPath(amoCode, auditKey, "closing")}
        exitLabel="Back to Closing"
        secondaryHref={auditSessionPath(amoCode, auditKey, "setup")}
        secondaryLabel="Open Setup"
      />
    );
  }

  return (
    <section className="qms-occurrence-stage" aria-label="Audit follow-up workspace">
      <header className="qms-occurrence-stage__header">
        <div><span>Follow-up</span><h2>Corrective action control</h2><p>Execution closure does not close corrective action. Track CAR ownership, milestones, extensions, escalation and effectiveness here.</p></div>
        <div className="qms-occurrence-stage__header-actions">
          <span>{closure.follow_up_status}</span>
          <Link className="qms-occurrence-stage__next" to={auditSessionPath(amoCode, auditKey, "archive")}>Open Archive</Link>
          <button type="button" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</button>
        </div>
      </header>

      {localError ? <div className="qms-occurrence-stage__message is-error" role="alert"><AlertTriangle size={15} /> {localError}</div> : null}
      {notice ? <div className="qms-occurrence-stage__message" role="status"><CheckCircle2 size={15} /> {notice}</div> : null}

      <div className="qms-occurrence-stage__metrics">
        <div><strong>{cars.length}</strong><span>Audit CARs</span></div>
        <div><strong>{openCars.length}</strong><span>Open</span></div>
        <div><strong>{overdueCars.length}</strong><span>Overdue</span></div>
        <div><strong>{escalatedCars.length}</strong><span>Escalated</span></div>
      </div>

      <div className="qms-occurrence-stage__grid">
        <main>
          <article className="qms-occurrence-stage__card">
            <header><Clock3 size={18} /><div><h3>Corrective-action queue</h3><small>One audit-filtered register query; detailed control-loop state is fetched only for the selected CAR.</small></div></header>
            {!cars.length ? <p>No CARs are linked to this audit.</p> : <div className="qms-occurrence-stage__queue">{cars.map((car) => <button type="button" key={car.id} className={car.id === effectiveSelectedCarId ? "is-selected" : ""} onClick={() => setSelectedCarId(car.id)}><div><strong>{car.car_number}</strong><span>{car.title}</span><small>{car.finding_ref || "No finding reference"} · {car.priority}</small></div><em data-state={carIsClosed(car) ? "closed" : carIsOverdue(car) ? "overdue" : "open"}>{carIsClosed(car) ? "Closed" : carIsOverdue(car) ? "Overdue" : car.status.replaceAll("_", " ")}</em></button>)}</div>}
          </article>

          {selectedCar ? <article className="qms-occurrence-stage__card">
            <header><ShieldAlert size={18} /><div><h3>{selectedCar.car_number} · control state</h3><small>{selectedCar.summary || selectedCar.title}</small></div></header>
            {selectedControlQuery.isLoading ? <p>Loading selected CAR control loop…</p> : selectedControlQuery.isError ? <div role="alert">{selectedControlQuery.error instanceof Error ? selectedControlQuery.error.message : "CAR control loop unavailable."}</div> : selectedControl ? <>
              <div className="qms-occurrence-stage__metrics is-compact"><div><strong>{selectedControl.health.state}</strong><span>Health</span></div><div><strong>{selectedControl.health.risk_score}</strong><span>Risk score</span></div><div><strong>{selectedControl.milestones.filter((row) => row.status === "COMPLETED").length}/{selectedControl.milestones.length}</strong><span>Milestones complete</span></div><div><strong>{selectedControl.deadline_changes.filter((row) => row.status === "PENDING").length}</strong><span>Extension decisions</span></div></div>
              <p><strong>Next required action:</strong> {selectedControl.health.next_action}</p>
              {selectedControl.closure_readiness.blockers.length ? <ul>{selectedControl.closure_readiness.blockers.map((blocker, index) => <li key={`${blocker.code}-${index}`}>{blocker.message}</li>)}</ul> : <p className="is-ready"><CheckCircle2 size={14} /> CAR closure gates are satisfied.</p>}
              <Link className="qms-occurrence-stage__next" to={`/maintenance/${encodeURIComponent(amoCode)}/quality/cars/${encodeURIComponent(selectedCar.id)}`}><ExternalLink size={15} /> Open full CAR control loop</Link>
            </> : null}
          </article> : null}
        </main>

        <aside>
          <article className="qms-occurrence-stage__card">
            <header><CheckCircle2 size={18} /><div><h3>Follow-up closure gate</h3><small>Computed by the backend from this audit's unresolved assurance obligations.</small></div></header>
            <dl><div><dt>Execution</dt><dd>{closure.execution_status}</dd></div><div><dt>Follow-up</dt><dd>{closure.follow_up_status}</dd></div></dl>
            {closure.follow_up_readiness.blockers.length ? <ul>{closure.follow_up_readiness.blockers.map((blocker, index) => <li key={`${blocker.type}-${blocker.id || index}`}><strong>{blocker.type}{blocker.ref ? ` · ${blocker.ref}` : ""}</strong><span>{blocker.reason}</span></li>)}</ul> : <p className="is-ready"><CheckCircle2 size={14} /> No unresolved follow-up blocker remains.</p>}
            {canManage ? <><label><span>Lifecycle decision reason</span><textarea rows={4} value={completionReason} onChange={(event) => setCompletionReason(event.target.value)} /></label><div className="qms-occurrence-stage__actions">{closure.execution_status === "CLOSED" && closure.follow_up_status !== "COMPLETE" ? <button type="button" className="is-primary" disabled={!closure.follow_up_readiness.ready || completionReason.trim().length < 8 || completeMutation.isPending} onClick={() => completeMutation.mutate()}><CheckCircle2 size={15} /> Complete follow-up</button> : null}{closure.follow_up_status === "COMPLETE" ? <button type="button" disabled={completionReason.trim().length < 8 || reopenMutation.isPending} onClick={() => reopenMutation.mutate()}><RotateCcw size={15} /> Reopen follow-up</button> : null}</div></> : null}
          </article>
        </aside>
      </div>
    </section>
  );
};

export default AuditFollowUpWorkspace;
