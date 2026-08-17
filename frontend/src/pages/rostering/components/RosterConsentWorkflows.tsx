import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, RefreshCw, ShieldCheck, X } from "lucide-react";

import {
  decideRosterConsentAsSupervisor,
  listMyRosterConsents,
  listSupervisorPendingRosterConsents,
  respondRosterConsent,
} from "../../../services/rosteringCompliance";
import type { RosterAssignmentConsentRead } from "../../../types/rosteringCompliance";
import { errorMessage, formatDateTime } from "../rosterUi";
import { StatusPill } from "./RosterShell";

const MY_CONSENTS_KEY = ["rostering", "consents", "me"] as const;
const SUPERVISOR_CONSENTS_KEY = ["rostering", "consents", "supervisor", "pending"] as const;

function dutyDuration(row: RosterAssignmentConsentRead): string {
  const minutes = Math.max(0, Math.round((Date.parse(row.planned_end) - Date.parse(row.planned_start)) / 60_000));
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function consentTone(value: string): "good" | "warning" | "blocker" | undefined {
  if (["ACCEPTED", "APPROVED", "NOT_REQUIRED"].includes(value)) return "good";
  if (["DECLINED", "REJECTED", "INVALIDATED"].includes(value)) return "blocker";
  return "warning";
}

function DutyTerms({ row }: { row: RosterAssignmentConsentRead }) {
  const prior = row.original_schedule_json || null;
  return (
    <div className="wr-form-grid wr-form-grid--inspector">
      <div><span className="wr-eyebrow">Duty type</span><strong>{row.duty_type.replace(/_/g, " ")}</strong></div>
      <div><span className="wr-eyebrow">Duration</span><strong>{dutyDuration(row)}</strong></div>
      <div className="wr-span-2"><span className="wr-eyebrow">Exact duty window</span><strong>{formatDateTime(row.planned_start)} → {formatDateTime(row.planned_end)}</strong></div>
      <div className="wr-span-2"><span className="wr-eyebrow">Reason</span><p>{row.reason}</p></div>
      {row.overtime_rest_day_classification ? <div><span className="wr-eyebrow">Pay classification</span><strong>{row.overtime_rest_day_classification.replace(/_/g, " ")}</strong></div> : null}
      {prior ? <div className="wr-span-2"><span className="wr-eyebrow">Changed from</span><p>{String(prior.planned_start || "—")} → {String(prior.planned_end || "—")}</p></div> : null}
      {row.replacement_rest_json && Object.keys(row.replacement_rest_json).length ? <div className="wr-span-2"><span className="wr-eyebrow">Required recovery / replacement rest</span><p>{JSON.stringify(row.replacement_rest_json)}</p></div> : null}
    </div>
  );
}

export function MyRosterConsentPanel() {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [comment, setComment] = useState<Record<string, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);
  const query = useQuery({
    queryKey: MY_CONSENTS_KEY,
    queryFn: listMyRosterConsents,
    staleTime: 20_000,
  });
  const rows = useMemo(() => {
    const source = query.data || [];
    return [...source].sort((left, right) => {
      const rank = (value: string) => value === "PENDING" ? 0 : value === "ACCEPTED" ? 1 : value === "DECLINED" ? 2 : 3;
      return rank(left.personnel_response) - rank(right.personnel_response) || Date.parse(right.created_at) - Date.parse(left.created_at);
    });
  }, [query.data]);
  const pending = rows.filter((row) => row.personnel_response === "PENDING");

  const decide = async (row: RosterAssignmentConsentRead, decision: "ACCEPT" | "DECLINE") => {
    setBusy(`${row.id}:${decision}`);
    setActionError(null);
    try {
      await respondRosterConsent(row.id, {
        decision,
        assignment_fingerprint: row.assignment_fingerprint,
        comment: comment[row.id]?.trim() || null,
      });
      await Promise.all([
        query.refetch(),
        queryClient.invalidateQueries({ queryKey: ["rostering", "workflow-gates"] }),
        queryClient.invalidateQueries({ queryKey: SUPERVISOR_CONSENTS_KEY }),
      ]);
    } catch (reason) {
      setActionError(errorMessage(reason));
      await query.refetch();
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="wr-panel" aria-labelledby="my-roster-consent-title">
      <div className="wr-section-heading">
        <div><span className="wr-eyebrow">Controlled duty acknowledgement</span><h2 id="my-roster-consent-title">Duty decisions requiring you</h2><p>Review the exact proposed duty before accepting or declining it.</p></div>
        <span className={`wr-count-badge${pending.length ? " is-danger" : ""}`}>{pending.length}</span>
      </div>
      <div className="wr-inline-warning"><ShieldCheck size={16} /><span>Your acknowledgement applies only to the exact duty shown. It does not legalize a roster that fails statutory duty or protected-rest limits, and it cannot override a hard compliance blocker.</span></div>
      {query.isPending ? <div className="wr-recommendation-loading"><RefreshCw size={14} className="is-spinning" /> Loading acknowledgement requests…</div> : null}
      {query.error ? <div className="wr-inline-error">{errorMessage(query.error)}</div> : null}
      {actionError ? <div className="wr-inline-error">{actionError}</div> : null}
      {!query.isPending && rows.length === 0 ? <div className="wr-success-note"><Check size={16} /> No roster acknowledgement is waiting for you.</div> : null}
      <div className="wr-recommendation-list">
        {rows.slice(0, 20).map((row) => (
          <article key={row.id} className="wr-recommendation">
            <div className="wr-section-heading"><div><strong>{row.duty_type.replace(/_/g, " ")}</strong><p>{formatDateTime(row.planned_start)}</p></div><StatusPill value={row.personnel_response} tone={consentTone(row.personnel_response)} /></div>
            <DutyTerms row={row} />
            <div className="wr-inline-counts"><StatusPill value={`Supervisor ${row.supervisor_decision.replace(/_/g, " ")}`} tone={consentTone(row.supervisor_decision)} />{row.invalidated_at ? <StatusPill value="STALE REVISION" tone="blocker" /> : null}</div>
            {row.personnel_response_at ? <small>Decision recorded {formatDateTime(row.personnel_response_at)}</small> : null}
            {row.invalidation_reason ? <div className="wr-inline-warning"><AlertTriangle size={14} /> {row.invalidation_reason.replace(/_/g, " ")}</div> : null}
            {row.personnel_response === "PENDING" ? (
              <>
                <label><span>Comment (optional)</span><textarea rows={2} value={comment[row.id] || ""} onChange={(event) => setComment((current) => ({ ...current, [row.id]: event.target.value }))} /></label>
                <div className="wr-actions">
                  <button type="button" className="wr-button wr-button--secondary" disabled={Boolean(busy)} onClick={() => void decide(row, "DECLINE")}><X size={15} /> Decline</button>
                  <button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy)} onClick={() => void decide(row, "ACCEPT")}><Check size={15} /> Accept exact duty</button>
                </div>
              </>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

export function SupervisorRosterConsentPanel() {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [comment, setComment] = useState<Record<string, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);
  const query = useQuery({
    queryKey: SUPERVISOR_CONSENTS_KEY,
    queryFn: listSupervisorPendingRosterConsents,
    staleTime: 15_000,
  });
  const rows = query.data || [];

  const decide = async (row: RosterAssignmentConsentRead, decision: "APPROVE" | "REJECT") => {
    setBusy(`${row.id}:${decision}`);
    setActionError(null);
    try {
      await decideRosterConsentAsSupervisor(row.id, {
        decision,
        assignment_fingerprint: row.assignment_fingerprint,
        comment: comment[row.id]?.trim() || null,
      });
      await Promise.all([
        query.refetch(),
        queryClient.invalidateQueries({ queryKey: ["rostering", "workflow-gates"] }),
      ]);
    } catch (reason) {
      setActionError(errorMessage(reason));
      await query.refetch();
    } finally {
      setBusy(null);
    }
  };

  if (!query.isPending && !query.error && rows.length === 0) return null;

  return (
    <section className="wr-panel" aria-labelledby="supervisor-roster-consent-title">
      <div className="wr-section-heading"><div><span className="wr-eyebrow">Scoped supervisor workflow</span><h2 id="supervisor-roster-consent-title">Duty approvals awaiting you</h2><p>Only assignments inside your permitted department/base scope appear here.</p></div><span className={`wr-count-badge${rows.length ? " is-danger" : ""}`}>{rows.length}</span></div>
      <div className="wr-inline-warning"><ShieldCheck size={16} /><span>Supervisor approval confirms the permitted workflow only. It never overrides a statutory hard blocker or substitutes for the employee’s own acknowledgement.</span></div>
      {query.isPending ? <div className="wr-recommendation-loading"><RefreshCw size={14} className="is-spinning" /> Loading scoped approvals…</div> : null}
      {query.error ? <div className="wr-inline-error">{errorMessage(query.error)}</div> : null}
      {actionError ? <div className="wr-inline-error">{actionError}</div> : null}
      <div className="wr-recommendation-list">
        {rows.map((row) => (
          <article key={row.id} className="wr-recommendation">
            <div className="wr-section-heading"><div><strong>Personnel {row.personnel_id}</strong><p>{row.reason}</p></div><StatusPill value="PERSONNEL ACCEPTED" tone="good" /></div>
            <DutyTerms row={row} />
            <label><span>Supervisor comment (optional)</span><textarea rows={2} value={comment[row.id] || ""} onChange={(event) => setComment((current) => ({ ...current, [row.id]: event.target.value }))} /></label>
            <div className="wr-actions"><button type="button" className="wr-button wr-button--secondary" disabled={Boolean(busy)} onClick={() => void decide(row, "REJECT")}><X size={15} /> Reject</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy)} onClick={() => void decide(row, "APPROVE")}><Check size={15} /> Approve workflow</button></div>
          </article>
        ))}
      </div>
    </section>
  );
}
