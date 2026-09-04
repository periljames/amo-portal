import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, CheckCircle2, ClipboardCheck, FileClock, History, PanelRightClose, PanelRightOpen, Send, ShieldAlert } from "lucide-react";

import {
  createAuditNotice,
  createAuditNoticePolicy,
  createAuditPreparationRevision,
  issueAuditPreparationRevision,
  listAuditNoticePolicies,
  listAuditNotices,
  listAuditPreparationRevisions,
  reviseAuditNotice,
  transitionAuditNotice,
  type AuditNotice,
} from "../../services/qmsAuditGovernance";
import { resolveAuditOccurrence } from "../../services/qmsAuditOccurrenceResolver";
import OccurrenceToolbarPortal, { AUDIT_PREPARE_TOOLBAR_ID } from "../../features/qms/auditSession/OccurrenceToolbarPortal";
import "../../styles/qms-audit-governance-panel.css";

type Props = { amoCode: string; auditKey: string; launcherPortalId?: string };
type PanelTab = "preparation" | "notices";

const todayKey = () => new Date().toISOString().slice(0, 10);
const displayDateTime = (value?: string | null) => value ? new Date(value).toLocaleString() : "—";

function nextNoticeActions(notice: AuditNotice): Array<AuditNotice["status"] | "SUBMIT" | "RETURN" | "APPROVE" | "GENERATE" | "DELIVER" | "ACKNOWLEDGE" | "CANCEL"> {
  switch (notice.status) {
    case "DRAFT": return ["SUBMIT", "CANCEL"];
    case "UNDER_REVIEW": return ["APPROVE", "RETURN", "CANCEL"];
    case "APPROVED": return ["GENERATE", "CANCEL"];
    case "GENERATED": return ["DELIVER", "CANCEL"];
    case "DELIVERED": return ["ACKNOWLEDGE"];
    default: return [];
  }
}

const QualityAuditGovernancePanelHost: React.FC<Props> = ({ amoCode, auditKey, launcherPortalId = AUDIT_PREPARE_TOOLBAR_ID }) => {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<PanelTab>("preparation");
  const [error, setError] = useState<string | null>(null);
  const [prepReason, setPrepReason] = useState("Capture controlled preparation sources for this audit.");
  const [prepScope, setPrepScope] = useState("");
  const [transitionReason, setTransitionReason] = useState("Governed audit notice lifecycle decision.");
  const [noticeDate, setNoticeDate] = useState(todayKey());
  const [noticeReason, setNoticeReason] = useState("Create controlled audit notice revision.");
  const [exceptionType, setExceptionType] = useState<"" | "EMERGENCY" | "UNANNOUNCED">("");
  const [exceptionReason, setExceptionReason] = useState("");
  const [deliveryChannel, setDeliveryChannel] = useState("EMAIL");
  const [deliveryReference, setDeliveryReference] = useState("");
  const [policyDays, setPolicyDays] = useState("14");

  const auditQuery = useQuery({
    queryKey: ["qms-audit-governance-resolve", amoCode, auditKey],
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const audit = auditQuery.data;
  const auditId = audit?.id || "";

  const prepQuery = useQuery({
    queryKey: ["qms-audit-preparation-revisions", amoCode, auditId],
    queryFn: ({ signal }) => listAuditPreparationRevisions(amoCode, auditId, signal),
    enabled: Boolean(auditId && open),
  });
  const noticeQuery = useQuery({
    queryKey: ["qms-audit-notices", amoCode, auditId],
    queryFn: ({ signal }) => listAuditNotices(amoCode, auditId, signal),
    enabled: Boolean(auditId && open),
  });
  const policyQuery = useQuery({
    queryKey: ["qms-audit-notice-policies", amoCode],
    queryFn: ({ signal }) => listAuditNoticePolicies(amoCode, signal),
    enabled: open,
  });

  const latestPrep = prepQuery.data?.items?.[0];
  const latestNotice = noticeQuery.data?.items?.[0];
  const activePolicy = useMemo(() => {
    const policies = policyQuery.data?.items || [];
    if (!audit) return policies[0];
    return policies.find((item) => item.audit_kind === audit.kind) || policies.find((item) => !item.audit_kind) || policies[0];
  }, [audit, policyQuery.data?.items]);

  const refresh = async () => {
    setError(null);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-preparation-revisions", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-notices", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-notice-policies", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-context", auditKey] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-preparation-context", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "audit-session", amoCode, auditId] }),
    ]);
  };

  const createPrep = useMutation({
    mutationFn: () => createAuditPreparationRevision(amoCode, auditId, { reason: prepReason, preparation_scope: prepScope || undefined }),
    onSuccess: () => void refresh(),
    onError: (cause: Error) => setError(cause.message),
  });
  const issuePrep = useMutation({
    mutationFn: () => latestPrep ? issueAuditPreparationRevision(amoCode, auditId, latestPrep.id, prepReason) : Promise.reject(new Error("No draft preparation revision exists.")),
    onSuccess: () => void refresh(),
    onError: (cause: Error) => setError(cause.message),
  });
  const saveNotice = useMutation({
    mutationFn: () => {
      const payload = {
        policy_id: activePolicy?.id,
        notice_date: noticeDate,
        exception_type: exceptionType || undefined,
        exception_reason: exceptionType ? exceptionReason : undefined,
        reason: noticeReason,
      } as const;
      return latestNotice && latestNotice.status !== "DRAFT"
        ? reviseAuditNotice(amoCode, auditId, latestNotice.id, payload)
        : createAuditNotice(amoCode, auditId, payload);
    },
    onSuccess: () => void refresh(),
    onError: (cause: Error) => setError(cause.message),
  });
  const noticeTransition = useMutation({
    mutationFn: (action: "SUBMIT" | "RETURN" | "APPROVE" | "GENERATE" | "DELIVER" | "ACKNOWLEDGE" | "CANCEL") => {
      if (!latestNotice) return Promise.reject(new Error("No notice revision exists."));
      return transitionAuditNotice(amoCode, auditId, latestNotice.id, {
        action,
        reason: transitionReason,
        delivery_channel: action === "DELIVER" ? deliveryChannel : undefined,
        delivery_reference: action === "DELIVER" ? deliveryReference : undefined,
      });
    },
    onSuccess: () => void refresh(),
    onError: (cause: Error) => setError(cause.message),
  });
  const createPolicy = useMutation({
    mutationFn: () => createAuditNoticePolicy(amoCode, {
      policy_code: `AUDIT_NOTICE_${policyDays}_DAY`,
      title: `${policyDays}-day audit notice policy`,
      minimum_notice_days: Math.max(0, Number(policyDays) || 14),
      review_required: true,
      acknowledgement_required: true,
      emergency_exception_allowed: true,
      unannounced_exception_allowed: true,
    }),
    onSuccess: () => void refresh(),
    onError: (cause: Error) => setError(cause.message),
  });

  if (!audit && auditQuery.isLoading) return null;
  if (!audit) return null;

  const actions = latestNotice ? nextNoticeActions(latestNotice).filter((item): item is "SUBMIT" | "RETURN" | "APPROVE" | "GENERATE" | "DELIVER" | "ACKNOWLEDGE" | "CANCEL" => !["DRAFT", "UNDER_REVIEW", "APPROVED", "GENERATED", "DELIVERED", "ACKNOWLEDGED", "SUPERSEDED", "CANCELLED"].includes(item as AuditNotice["status"])) : [];

  const launcher = (
    <button
      className="qms-audit-governance-launcher qms-occurrence-toolbar-btn"
      type="button"
      onClick={() => setOpen((value) => !value)}
      aria-expanded={open}
      aria-controls="qms-audit-governance-panel"
    >
      {open ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />}
      Governance
    </button>
  );

  return (
    <>
      {launcherPortalId ? (
        <OccurrenceToolbarPortal containerId={launcherPortalId}>{launcher}</OccurrenceToolbarPortal>
      ) : launcher}
      {open ? (
        <aside id="qms-audit-governance-panel" className="qms-audit-governance-panel" aria-label="Audit governance">
          <header>
            <div>
              <span>Controlled audit lifecycle</span>
              <strong>{audit.audit_ref} · {audit.title}</strong>
            </div>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close audit governance panel"><PanelRightClose size={18} /></button>
          </header>

          <nav aria-label="Audit governance sections">
            <button type="button" className={tab === "preparation" ? "is-active" : ""} onClick={() => setTab("preparation")}><ClipboardCheck size={16} /> Preparation</button>
            <button type="button" className={tab === "notices" ? "is-active" : ""} onClick={() => setTab("notices")}><BellRing size={16} /> Notices</button>
          </nav>

          {error ? <div className="qms-audit-governance-error" role="alert"><ShieldAlert size={17} /> {error}</div> : null}

          {tab === "preparation" ? (
            <div className="qms-audit-governance-body">
              <section className="qms-audit-governance-card">
                <div className="qms-audit-governance-card__heading">
                  <div><FileClock size={18} /><strong>Controlled source snapshot</strong></div>
                  <span>{latestPrep ? `Rev ${latestPrep.revision_no} · ${latestPrep.status}` : "Not issued"}</span>
                </div>
                <p>Freeze the exact scope, criteria, assigned personnel, checklist rows and document requests used to prepare this audit.</p>
                <label>Preparation scope / notes<textarea value={prepScope} onChange={(event) => setPrepScope(event.target.value)} placeholder="Sampling focus, prior findings, records to inspect, opening-meeting preparation…" /></label>
                <label>Change / issue reason<textarea value={prepReason} onChange={(event) => setPrepReason(event.target.value)} /></label>
                <div className="qms-audit-governance-actions">
                  {!latestPrep || latestPrep.status === "ISSUED" ? <button type="button" onClick={() => createPrep.mutate()} disabled={createPrep.isPending || prepReason.trim().length < 8}>Create controlled revision</button> : null}
                  {latestPrep?.status === "DRAFT" ? <button type="button" className="is-primary" onClick={() => issuePrep.mutate()} disabled={issuePrep.isPending || prepReason.trim().length < 8}>Issue revision</button> : null}
                </div>
              </section>

              {latestPrep ? (
                <section className="qms-audit-governance-card">
                  <div className="qms-audit-governance-card__heading"><div><History size={18} /><strong>Latest evidence package</strong></div><span>{displayDateTime(latestPrep.issued_at || latestPrep.created_at)}</span></div>
                  <dl className="qms-audit-governance-stats">
                    <div><dt>Checklist rows</dt><dd>{latestPrep.checklist_snapshot.length}</dd></div>
                    <div><dt>Document requests</dt><dd>{latestPrep.document_request_snapshot.length}</dd></div>
                    <div><dt>Source links</dt><dd>{latestPrep.source_references.length}</dd></div>
                  </dl>
                  <code className="qms-audit-governance-hash" title={latestPrep.source_fingerprint}>{latestPrep.source_fingerprint}</code>
                  <ol className="qms-audit-governance-history">
                    {latestPrep.events.map((event) => <li key={event.id}><strong>{event.event_type}</strong><span>{event.reason}</span><time>{displayDateTime(event.created_at)}</time></li>)}
                  </ol>
                </section>
              ) : null}
            </div>
          ) : (
            <div className="qms-audit-governance-body">
              <section className="qms-audit-governance-card">
                <div className="qms-audit-governance-card__heading"><div><BellRing size={18} /><strong>Notice policy</strong></div><span>{activePolicy ? `${activePolicy.minimum_notice_days} days` : "System default · 14 days"}</span></div>
                {activePolicy ? <p>{activePolicy.title}. Review {activePolicy.review_required ? "required" : "not required"}; acknowledgement {activePolicy.acknowledgement_required ? "required" : "optional"}.</p> : (
                  <>
                    <p>No tenant policy is configured. The backend will enforce the conservative 14-day default until a policy is created.</p>
                    <div className="qms-audit-governance-inline"><label>Minimum days<input type="number" min={0} max={365} value={policyDays} onChange={(event) => setPolicyDays(event.target.value)} /></label><button type="button" onClick={() => createPolicy.mutate()} disabled={createPolicy.isPending}>Create tenant policy</button></div>
                  </>
                )}
              </section>

              <section className="qms-audit-governance-card">
                <div className="qms-audit-governance-card__heading"><div><FileClock size={18} /><strong>{latestNotice ? `Notice revision ${latestNotice.revision_no}` : "Create notice"}</strong></div><span>{latestNotice?.status || "DRAFT"}</span></div>
                <label>Notice date<input type="date" value={noticeDate} onChange={(event) => setNoticeDate(event.target.value)} /></label>
                <label>Exception<select value={exceptionType} onChange={(event) => setExceptionType(event.target.value as typeof exceptionType)}><option value="">None — enforce notice period</option><option value="EMERGENCY">Emergency</option><option value="UNANNOUNCED">Unannounced audit</option></select></label>
                {exceptionType ? <label>Exception reason<textarea value={exceptionReason} onChange={(event) => setExceptionReason(event.target.value)} placeholder="State the controlled justification and approval basis." /></label> : null}
                <label>Lifecycle reason<textarea value={noticeReason} onChange={(event) => setNoticeReason(event.target.value)} /></label>
                {(!latestNotice || latestNotice.status !== "DRAFT") ? <button type="button" onClick={() => saveNotice.mutate()} disabled={saveNotice.isPending || noticeReason.trim().length < 8 || Boolean(exceptionType && exceptionReason.trim().length < 8)}>{latestNotice ? "Create revised notice" : "Create notice draft"}</button> : null}
              </section>

              {latestNotice ? (
                <section className="qms-audit-governance-card">
                  <div className="qms-audit-governance-card__heading"><div><Send size={18} /><strong>Governed progression</strong></div><span>{latestNotice.required_notice_days}-day requirement</span></div>
                  <p><strong>{latestNotice.subject}</strong></p>
                  <label>Decision / transition reason<textarea value={transitionReason} onChange={(event) => setTransitionReason(event.target.value)} /></label>
                  {latestNotice.status === "GENERATED" ? <div className="qms-audit-governance-inline"><label>Channel<input value={deliveryChannel} onChange={(event) => setDeliveryChannel(event.target.value)} /></label><label>Delivery reference<input value={deliveryReference} onChange={(event) => setDeliveryReference(event.target.value)} placeholder="Message ID / dispatch ref" /></label></div> : null}
                  <div className="qms-audit-governance-actions">
                    {actions.map((action) => <button key={action} type="button" className={["APPROVE", "GENERATE", "DELIVER", "ACKNOWLEDGE"].includes(action) ? "is-primary" : ""} onClick={() => noticeTransition.mutate(action)} disabled={noticeTransition.isPending || transitionReason.trim().length < 8 || (action === "DELIVER" && deliveryReference.trim().length < 3)}>{action.replaceAll("_", " ")}</button>)}
                  </div>
                  <ol className="qms-audit-governance-history">
                    {latestNotice.events.map((event) => <li key={event.id}><strong>{event.event_type}</strong><span>{event.reason}</span><time>{displayDateTime(event.created_at)}</time></li>)}
                  </ol>
                  {latestNotice.status === "ACKNOWLEDGED" ? <div className="qms-audit-governance-success"><CheckCircle2 size={17} /> Delivery and acknowledgement are attributable and retained in revision history.</div> : null}
                </section>
              ) : null}
            </div>
          )}
        </aside>
      ) : null}
    </>
  );
};

export default QualityAuditGovernancePanelHost;
