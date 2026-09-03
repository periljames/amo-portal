import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileCheck2, History, PanelRightClose, PanelRightOpen, RefreshCw, RotateCcw, ShieldAlert } from "lucide-react";

import {
  adoptCurrentAuditReport,
  getAuditClosureState,
  listAuditReportRevisions,
  recordAuditExecutionClosed,
  recordAuditFollowUpComplete,
  reopenAuditFollowUp,
  transitionAuditReport,
  type AuditClosureState,
  type AuditReportRevision,
} from "../../services/qmsAuditCloseout";
import { resolveAuditOccurrence } from "../../services/qmsAuditOccurrenceResolver";
import "../../styles/qms-audit-report-closeout.css";

type Props = { amoCode: string; auditKey: string };
type Tab = "report" | "closeout";
type AuditReportRevisionList = { items: AuditReportRevision[] };

function message(error: unknown): string {
  return error instanceof Error ? error.message : "The governed audit action could not be completed.";
}

function nextActions(row: AuditReportRevision): Array<"SUBMIT" | "RETURN" | "APPROVE" | "ISSUE" | "CANCEL"> {
  if (row.status === "DRAFT") return ["SUBMIT", "CANCEL"];
  if (row.status === "INTERNAL_REVIEW") return ["APPROVE", "RETURN", "CANCEL"];
  if (row.status === "APPROVED") return ["ISSUE", "RETURN", "CANCEL"];
  return [];
}

const QualityAuditReportCloseoutHost: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("report");
  const [reason, setReason] = useState("Governed audit report / assurance lifecycle decision.");
  const [error, setError] = useState("");

  const auditQuery = useQuery({
    queryKey: ["qms-audit-closeout-resolve", amoCode, auditKey],
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const audit = auditQuery.data;
  const auditId = audit?.id || "";
  const reportQueryKey = ["qms-audit-report-revisions", amoCode, auditId] as const;
  const closureQueryKey = ["qms-audit-closure-state", amoCode, auditId] as const;

  const reportQuery = useQuery({
    queryKey: reportQueryKey,
    queryFn: ({ signal }) => listAuditReportRevisions(amoCode, auditId, signal),
    enabled: Boolean(open && auditId),
  });
  const closureQuery = useQuery({
    queryKey: closureQueryKey,
    queryFn: ({ signal }) => getAuditClosureState(amoCode, auditId, signal),
    enabled: Boolean(open && auditId),
  });

  const latest = reportQuery.data?.items?.[0];
  const issued = reportQuery.data?.items?.find((row) => row.status === "ISSUED");
  const closure = closureQuery.data;

  const cacheReportRevision = (revision: AuditReportRevision) => {
    queryClient.setQueryData<AuditReportRevisionList>(reportQueryKey, (current) => {
      const remaining = (current?.items || []).filter((row) => row.id !== revision.id);
      return { items: [revision, ...remaining].sort((left, right) => right.revision_no - left.revision_no) };
    });
  };

  const cacheClosureState = (next: AuditClosureState) => {
    queryClient.setQueryData<AuditClosureState>(closureQueryKey, next);
  };

  const refresh = async () => {
    setError("");
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: reportQueryKey }),
      queryClient.invalidateQueries({ queryKey: closureQueryKey }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-context", auditKey] }),
    ]);
  };

  const adopt = useMutation({
    mutationFn: () => adoptCurrentAuditReport(amoCode, auditId, reason),
    onSuccess: (revision) => {
      cacheReportRevision(revision);
      void refresh();
    },
    onError: (cause) => setError(message(cause)),
  });
  const transition = useMutation({
    mutationFn: (action: "SUBMIT" | "RETURN" | "APPROVE" | "ISSUE" | "CANCEL") => latest ? transitionAuditReport(amoCode, auditId, latest.id, action, reason) : Promise.reject(new Error("No governed report revision exists.")),
    onSuccess: (revision) => {
      cacheReportRevision(revision);
      void refresh();
    },
    onError: (cause) => setError(message(cause)),
  });
  const executionClose = useMutation({
    mutationFn: () => recordAuditExecutionClosed(amoCode, auditId, reason),
    onSuccess: (next) => {
      cacheClosureState(next);
      void refresh();
    },
    onError: (cause) => setError(message(cause)),
  });
  const followUpComplete = useMutation({
    mutationFn: () => recordAuditFollowUpComplete(amoCode, auditId, reason),
    onSuccess: (next) => {
      cacheClosureState(next);
      void refresh();
    },
    onError: (cause) => setError(message(cause)),
  });
  const reopen = useMutation({
    mutationFn: () => reopenAuditFollowUp(amoCode, auditId, reason),
    onSuccess: (next) => {
      cacheClosureState(next);
      void refresh();
    },
    onError: (cause) => setError(message(cause)),
  });

  if (!audit) return null;
  const pending = adopt.isPending || transition.isPending || executionClose.isPending || followUpComplete.isPending || reopen.isPending;

  return (
    <>
      <button className="qms-audit-closeout-launcher" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="qms-audit-report-closeout-panel">
        {open ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />} Report & closeout
      </button>
      {open ? <aside id="qms-audit-report-closeout-panel" className="qms-audit-closeout-panel" aria-label="Audit report and assurance closeout">
        <header><div><span>Governed audit completion</span><strong>{audit.audit_ref} · {audit.title}</strong></div><button type="button" onClick={() => setOpen(false)} aria-label="Close report and closeout panel"><PanelRightClose size={18} /></button></header>
        <nav>
          <button type="button" className={tab === "report" ? "is-active" : ""} onClick={() => setTab("report")}><FileCheck2 size={16} /> Report</button>
          <button type="button" className={tab === "closeout" ? "is-active" : ""} onClick={() => setTab("closeout")}><CheckCircle2 size={16} /> Closeout</button>
        </nav>
        {error ? <div className="qms-audit-closeout-error" role="alert"><ShieldAlert size={17} /> {error}</div> : null}
        <div className="qms-audit-closeout-body">
          <label>Decision reason<textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          {tab === "report" ? <>
            <section className="qms-audit-closeout-card">
              <header><div><FileCheck2 size={18} /><strong>Formal report revision</strong></div><span>{latest ? `Rev ${latest.revision_no} · ${latest.status}` : "No governed revision"}</span></header>
              <p>The existing audit report upload remains the file intake. Adopt it here to create an immutable checksum-backed report revision before internal review and formal issue.</p>
              <div className="qms-audit-closeout-actions">
                {(!latest || ["ISSUED", "SUPERSEDED", "CANCELLED"].includes(latest.status)) ? <button type="button" onClick={() => adopt.mutate()} disabled={pending || reason.trim().length < 8}>Adopt current upload</button> : null}
                {latest ? nextActions(latest).map((action) => <button key={action} type="button" className={["APPROVE", "ISSUE"].includes(action) ? "is-primary" : ""} onClick={() => transition.mutate(action)} disabled={pending || reason.trim().length < 8}>{action}</button>) : null}
              </div>
              {latest ? <dl><div><dt>File</dt><dd>{latest.filename}</dd></div><div><dt>SHA-256</dt><dd><code>{latest.sha256}</code></dd></div><div><dt>Issued</dt><dd>{latest.issued_at ? new Date(latest.issued_at).toLocaleString() : "Not issued"}</dd></div></dl> : null}
            </section>
            <section className="qms-audit-closeout-card">
              <header><div><History size={18} /><strong>Report history</strong></div><span>{reportQuery.data?.items.length ?? 0} revisions</span></header>
              <ol>{reportQuery.data?.items.map((row) => <li key={row.id}><strong>Rev {row.revision_no} · {row.status}</strong><span>{row.filename}</span><small>{row.events.map((event) => event.event_type).join(" → ") || "No events"}</small></li>)}</ol>
            </section>
          </> : <>
            <section className="qms-audit-closeout-card">
              <header><div><CheckCircle2 size={18} /><strong>Audit execution</strong></div><span>{closure?.execution_status || "OPEN"}</span></header>
              <p>Execution closure is recorded only after the authoritative audit engine has closed the audit and any governed report revision is formally issued.</p>
              {closure?.execution_readiness.blockers.length ? <ul>{closure.execution_readiness.blockers.map((blocker, index) => <li key={`${blocker.type}-${index}`}><strong>{blocker.type}</strong> · {blocker.reason}</li>)}</ul> : <p className="is-ready">Execution close evidence is ready.</p>}
              {closure?.execution_status !== "CLOSED" ? <button type="button" className="is-primary" onClick={() => executionClose.mutate()} disabled={pending || !closure?.execution_readiness.ready || reason.trim().length < 8}>Record execution closed</button> : null}
            </section>
            <section className="qms-audit-closeout-card">
              <header><div><RefreshCw size={18} /><strong>Assurance follow-up</strong></div><span>{closure?.follow_up_status || "OPEN"}</span></header>
              <p>This state is independent from audit execution. Open findings, CARs, Assurance Cases or ineffective/inconclusive effectiveness plans remain blockers.</p>
              {closure?.follow_up_readiness.blockers.length ? <ul>{closure.follow_up_readiness.blockers.map((blocker, index) => <li key={`${blocker.type}-${blocker.id || index}`}><strong>{blocker.type}{blocker.ref ? ` · ${blocker.ref}` : ""}</strong> · {blocker.reason}</li>)}</ul> : <p className="is-ready">No unresolved follow-up obligations were found.</p>}
              <div className="qms-audit-closeout-actions">
                {closure?.execution_status === "CLOSED" && closure.follow_up_status !== "COMPLETE" ? <button type="button" className="is-primary" onClick={() => followUpComplete.mutate()} disabled={pending || !closure.follow_up_readiness.ready || reason.trim().length < 8}>Complete assurance follow-up</button> : null}
                {closure?.follow_up_status === "COMPLETE" ? <button type="button" onClick={() => reopen.mutate()} disabled={pending || reason.trim().length < 8}><RotateCcw size={15} /> Reopen follow-up</button> : null}
              </div>
            </section>
            {closure?.events.length ? <section className="qms-audit-closeout-card"><header><div><History size={18} /><strong>Closure history</strong></div></header><ol>{closure.events.map((event) => <li key={event.id}><strong>{event.event_type}</strong><span>{event.reason}</span><small>{new Date(event.created_at).toLocaleString()}</small></li>)}</ol></section> : null}
          </>}
          <button type="button" className="qms-audit-closeout-refresh" onClick={() => void refresh()} disabled={pending}><RefreshCw size={15} /> Refresh evidence</button>
          {issued ? <small>Current formally issued report: revision {issued.revision_no}, checksum retained.</small> : null}
        </div>
      </aside> : null}
    </>
  );
};

export default QualityAuditReportCloseoutHost;