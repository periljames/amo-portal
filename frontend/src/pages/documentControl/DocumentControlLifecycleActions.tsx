import { useMemo, useState, type FormEvent } from "react";
import { Archive, CheckCircle2, Copy, FileClock, Landmark, Play, Plus, Send, ShieldCheck } from "lucide-react";

import {
  completeDocumentReview,
  createAuthoritySubmission,
  createControlledCopy,
  createControlledCopyEvent,
  createDocumentReview,
  createDocumentWorkflow,
  createTemporaryRevision,
  transitionDocumentWorkflow,
  transitionTemporaryRevision,
  updateAuthoritySubmission,
  type DocumentDetailResponse,
} from "../../services/documentControl";
import { DocumentControlEmpty, DocumentControlStatus } from "./DocumentControlShell";

export type LifecycleView = "workflow" | "authority" | "temporary-revisions" | "copies" | "reviews";

type Props = {
  detail: DocumentDetailResponse;
  tenant: string;
  activeView: LifecycleView;
  onChanged: () => void;
};

type ActionOption = { action: string; label: string; danger?: boolean };

const WORKFLOW_ACTIONS: Record<string, ActionOption[]> = {
  DRAFT: [{ action: "SUBMIT_TECHNICAL_REVIEW", label: "Submit technical review" }],
  TECHNICAL_REVIEW: [
    { action: "APPROVE_TECHNICAL", label: "Approve technical review" },
    { action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true },
  ],
  CORRECTIONS_REQUIRED: [{ action: "RESUBMIT_TECHNICAL_REVIEW", label: "Resubmit technical review" }],
  TECHNICAL_APPROVED: [{ action: "START_QUALITY_REVIEW", label: "Start Quality review" }],
  QUALITY_REVIEW: [
    { action: "APPROVE_QUALITY", label: "Approve Quality review" },
    { action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true },
  ],
  QUALITY_APPROVED: [{ action: "SUBMIT_ACCOUNTABLE_MANAGER", label: "Submit to Accountable Manager" }],
  ACCOUNTABLE_MANAGER_APPROVAL: [
    { action: "APPROVE_ACCOUNTABLE_MANAGER", label: "Approve and schedule" },
    { action: "MARK_AUTHORITY_SUBMITTED", label: "Confirm authority submission" },
    { action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true },
  ],
  AUTHORITY_SUBMITTED: [
    { action: "MARK_AUTHORITY_APPROVED", label: "Confirm authority approval" },
    { action: "REQUEST_CORRECTIONS", label: "Return for corrections", danger: true },
  ],
  AUTHORITY_APPROVED: [{ action: "SCHEDULE_EFFECTIVITY", label: "Schedule effectivity" }],
  SCHEDULED_FOR_EFFECTIVITY: [
    { action: "PUBLISH", label: "Publish revision" },
    { action: "REQUEST_CORRECTIONS", label: "Return for corrections", danger: true },
  ],
  PUBLISHED: [{ action: "ARCHIVE", label: "Archive revision", danger: true }],
};

const AUTHORITY_NEXT: Record<string, string[]> = {
  DRAFT: ["SUBMITTED", "WITHDRAWN"],
  SUBMITTED: ["IN_REVIEW", "QUERY_RECEIVED", "APPROVED", "REJECTED", "WITHDRAWN"],
  IN_REVIEW: ["QUERY_RECEIVED", "APPROVED", "REJECTED", "WITHDRAWN"],
  QUERY_RECEIVED: ["SUBMITTED", "IN_REVIEW", "APPROVED", "REJECTED", "WITHDRAWN"],
};

const TR_NEXT: Record<string, string[]> = {
  DRAFT: ["IN_REVIEW", "WITHDRAWN"],
  IN_REVIEW: ["DRAFT", "APPROVED", "WITHDRAWN"],
  APPROVED: ["IN_FORCE", "WITHDRAWN"],
  IN_FORCE: ["EXPIRED", "WITHDRAWN", "INCORPORATED"],
  EXPIRED: ["INCORPORATED", "WITHDRAWN"],
};

const COPY_EVENTS: Record<string, string[]> = {
  ISSUED: ["TRANSFER", "LOCATION_CHANGE", "RECALL", "RETURN", "WITHDRAW", "DESTROY"],
  RECALLED: ["RETURN", "WITHDRAW", "DESTROY"],
  RETURNED: ["WITHDRAW", "DESTROY"],
  WITHDRAWN: ["DESTROY"],
};

function evidenceFrom(value: string): Array<{ asset_id: string }> {
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((asset_id) => ({ asset_id }));
}

function idsFrom(value: string): string[] {
  return value.split(/[\s,;]+/).map((item) => item.trim()).filter(Boolean);
}

function useMutation(onChanged: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The controlled action failed.");
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

function ErrorMessage({ message }: { message: string }) {
  return message ? <div className="dc-form__error">{message}</div> : null;
}

export default function DocumentControlLifecycleActions({ detail, tenant, activeView, onChanged }: Props) {
  if (activeView === "workflow") return <WorkflowActions detail={detail} tenant={tenant} onChanged={onChanged} />;
  if (activeView === "authority") return <AuthorityActions detail={detail} tenant={tenant} onChanged={onChanged} />;
  if (activeView === "temporary-revisions") return <TemporaryRevisionActions detail={detail} tenant={tenant} onChanged={onChanged} />;
  if (activeView === "copies") return <ControlledCopyActions detail={detail} tenant={tenant} onChanged={onChanged} />;
  return <ReviewActions detail={detail} tenant={tenant} onChanged={onChanged} />;
}

function WorkflowActions({ detail, tenant, onChanged }: Omit<Props, "activeView">) {
  const latest = detail.document.latest_revision;
  const workflow = detail.workflows[0];
  const mutation = useMutation(onChanged);
  const [comments, setComments] = useState("");
  const [evidence, setEvidence] = useState("");
  const [effectiveAt, setEffectiveAt] = useState("");
  const [training, setTraining] = useState(workflow?.training_readiness_status || "NOT_REQUIRED");
  const [qms, setQms] = useState(workflow?.qms_readiness_status || "NOT_REQUIRED");

  if (!latest) return <DocumentControlEmpty title="No revision exists" message="Upload a source revision before creating a controlled workflow." />;
  if (!workflow) {
    return <div className="dc-form"><div className="dc-callout"><Play size={17} /><div><strong>Start controlled review.</strong> The workflow is tied to revision {latest.revision_number} and inherits the document's authority requirement.</div></div><div className="dc-form__actions"><button type="button" className="dc-button dc-button--primary" disabled={mutation.busy || latest.immutable} onClick={() => void mutation.run(() => createDocumentWorkflow(tenant, { manual_id: detail.document.id, revision_id: latest.id, requires_authority: detail.document.profile.requires_authority_approval, training_impact_required: false, training_readiness_status: "NOT_REQUIRED", qms_readiness_status: "NOT_REQUIRED", distribution_readiness_status: "NOT_REQUIRED" }))}><Play size={14} /> Start revision workflow</button></div><ErrorMessage message={mutation.error} /></div>;
  }

  const actions = WORKFLOW_ACTIONS[workflow.state] || [];
  const transition = (item: ActionOption) => mutation.run(() => transitionDocumentWorkflow(tenant, workflow.id, {
    action: item.action,
    comments: comments.trim() || null,
    evidence: evidenceFrom(evidence),
    expected_version: workflow.version,
    effective_at: effectiveAt ? new Date(effectiveAt).toISOString() : undefined,
    training_readiness_status: training,
    qms_readiness_status: qms,
    // Distribution readiness is managed only by campaign issuance on the server.
    distribution_readiness_status: workflow.distribution_readiness_status,
  }));

  return <div className="dc-form">
    <div className="dc-callout"><ShieldCheck size={17} /><div><strong>{workflow.state.replaceAll("_", " ")}</strong><div>Version {workflow.version} · Distribution readiness: {workflow.distribution_readiness_status}</div></div></div>
    <label className="wide"><span>Decision comments or waiver reason</span><textarea value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Explain the decision, correction, waiver, or release basis." /></label>
    <label className="wide"><span>Evidence asset IDs</span><textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} placeholder="One retained evidence asset ID per line" /></label>
    <label><span>Training readiness</span><select value={training} onChange={(event) => setTraining(event.target.value)}><option>NOT_REQUIRED</option><option>PENDING</option><option>BLOCKED</option><option>READY</option><option>WAIVED</option></select></label>
    <label><span>QMS readiness</span><select value={qms} onChange={(event) => setQms(event.target.value)}><option>NOT_REQUIRED</option><option>PENDING</option><option>BLOCKED</option><option>READY</option><option>WAIVED</option></select></label>
    <label><span>Scheduled effectivity</span><input type="datetime-local" value={effectiveAt} onChange={(event) => setEffectiveAt(event.target.value)} /></label>
    <label><span>Distribution readiness</span><input value={workflow.distribution_readiness_status} readOnly /><small>Established by issuing a real campaign; it cannot be marked ready here.</small></label>
    <ErrorMessage message={mutation.error} />
    <div className="dc-form__actions">{actions.map((item) => <button type="button" key={item.action} className={`dc-button ${item.danger ? "dc-button--danger" : "dc-button--primary"}`} disabled={mutation.busy} onClick={() => void transition(item)}>{item.label}</button>)}</div>
  </div>;
}

function AuthorityActions({ detail, tenant, onChanged }: Omit<Props, "activeView">) {
  const revision = detail.document.latest_revision;
  const workflow = detail.workflows[0];
  const mutation = useMutation(onChanged);
  const [authorityName, setAuthorityName] = useState("Kenya Civil Aviation Authority");
  const [reference, setReference] = useState("");
  const [responseDue, setResponseDue] = useState("");
  const [selectedId, setSelectedId] = useState(detail.authority_submissions[0]?.id || "");
  const selected = detail.authority_submissions.find((row) => row.id === selectedId) || detail.authority_submissions[0];
  const available = selected ? AUTHORITY_NEXT[selected.status] || [] : [];
  const [nextStatus, setNextStatus] = useState(available[0] || "SUBMITTED");
  const [summary, setSummary] = useState("");
  const [evidence, setEvidence] = useState("");

  const create = (event: FormEvent) => {
    event.preventDefault();
    if (!revision) return;
    void mutation.run(() => createAuthoritySubmission(tenant, { manual_id: detail.document.id, revision_id: revision.id, workflow_id: workflow?.id || null, authority_name: authorityName, submission_reference: reference, response_due_at: responseDue ? new Date(responseDue).toISOString() : null, evidence: [] }));
  };
  const update = () => {
    if (!selected) return;
    void mutation.run(() => updateAuthoritySubmission(tenant, selected.id, { status: nextStatus, response_summary: summary.trim() || null, response_due_at: responseDue ? new Date(responseDue).toISOString() : null, evidence: evidenceFrom(evidence) }));
  };

  return <div className="dc-grid">
    <form className="dc-form" onSubmit={create}>
      <label><span>Authority</span><input value={authorityName} onChange={(event) => setAuthorityName(event.target.value)} required /></label>
      <label><span>Submission reference</span><input value={reference} onChange={(event) => setReference(event.target.value)} required /></label>
      <label><span>Response due</span><input type="datetime-local" value={responseDue} onChange={(event) => setResponseDue(event.target.value)} /></label>
      <ErrorMessage message={mutation.error} />
      <div className="dc-form__actions"><button type="submit" className="dc-button" disabled={mutation.busy || !revision}><Plus size={14} /> Create draft submission</button></div>
    </form>
    {selected ? <div className="dc-form">
      <label className="wide"><span>Submission to update</span><select value={selected.id} onChange={(event) => { setSelectedId(event.target.value); setNextStatus(""); }}>{detail.authority_submissions.map((row) => <option key={row.id} value={row.id}>{row.authority_name} · {row.submission_reference} · {row.status}</option>)}</select></label>
      <label><span>Next authority status</span><select value={nextStatus} onChange={(event) => setNextStatus(event.target.value)}>{available.map((status) => <option key={status}>{status}</option>)}</select></label>
      <label className="wide"><span>Authority response, approval reference, or disposition reason</span><textarea value={summary} onChange={(event) => setSummary(event.target.value)} /></label>
      <label className="wide"><span>Submission or response evidence asset IDs</span><textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} placeholder="One evidence asset ID per line" /></label>
      <div className="dc-form__actions"><button type="button" className="dc-button dc-button--primary" disabled={mutation.busy || !nextStatus} onClick={update}><Landmark size={14} /> Record authority status</button></div>
    </div> : <DocumentControlEmpty title="No authority submission" message="Create a draft submission record against the current revision." />}
  </div>;
}

function TemporaryRevisionActions({ detail, tenant, onChanged }: Omit<Props, "activeView">) {
  const current = detail.document.latest_revision;
  const mutation = useMutation(onChanged);
  const [number, setNumber] = useState("");
  const [title, setTitle] = useState("");
  const [reason, setReason] = useState("");
  const [effective, setEffective] = useState("");
  const [expiry, setExpiry] = useState("");
  const [selectedId, setSelectedId] = useState(detail.temporary_revisions[0]?.id || "");
  const selected = detail.temporary_revisions.find((row) => row.id === selectedId) || detail.temporary_revisions[0];
  const nextStates = selected ? TR_NEXT[selected.status] || [] : [];
  const [nextStatus, setNextStatus] = useState(nextStates[0] || "IN_REVIEW");
  const [campaignId, setCampaignId] = useState("");
  const [incorporatedRevisionId, setIncorporatedRevisionId] = useState("");

  const create = (event: FormEvent) => {
    event.preventDefault();
    if (!current) return;
    void mutation.run(() => createTemporaryRevision(tenant, { manual_id: detail.document.id, base_revision_id: current.id, tr_number: number, title, reason, affected_sections: [], effective_date: effective, expiry_date: expiry }));
  };
  const transition = () => {
    if (!selected) return;
    void mutation.run(() => transitionTemporaryRevision(tenant, selected.id, { status: nextStatus, approval_status: nextStatus === "APPROVED" ? "APPROVED" : undefined, distribution_campaign_id: campaignId || null, incorporated_revision_id: incorporatedRevisionId || null }));
  };

  return <div className="dc-grid">
    <form className="dc-form" onSubmit={create}><label><span>TR number</span><input value={number} onChange={(event) => setNumber(event.target.value)} required /></label><label><span>Effective date</span><input type="date" value={effective} onChange={(event) => setEffective(event.target.value)} required /></label><label className="wide"><span>Subject</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label><label className="wide"><span>Reason and filing instruction</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} required /></label><label><span>Expiry or incorporation due</span><input type="date" value={expiry} onChange={(event) => setExpiry(event.target.value)} required /></label><ErrorMessage message={mutation.error} /><div className="dc-form__actions"><button type="submit" className="dc-button" disabled={mutation.busy || !current}><Plus size={14} /> Create temporary revision</button></div></form>
    {selected ? <div className="dc-form"><label className="wide"><span>Temporary revision</span><select value={selected.id} onChange={(event) => { setSelectedId(event.target.value); setNextStatus(""); }}>{detail.temporary_revisions.map((row) => <option key={row.id} value={row.id}>{row.tr_number} · {row.status} · expires {row.expiry_date}</option>)}</select></label><label><span>Next status</span><select value={nextStatus} onChange={(event) => setNextStatus(event.target.value)}>{nextStates.map((status) => <option key={status}>{status}</option>)}</select></label><label><span>Issued campaign ID</span><input value={campaignId} onChange={(event) => setCampaignId(event.target.value)} placeholder="Required before IN_FORCE" /></label><label className="wide"><span>Incorporating permanent revision ID</span><input value={incorporatedRevisionId} onChange={(event) => setIncorporatedRevisionId(event.target.value)} placeholder="Required before INCORPORATED" /></label><div className="dc-form__actions"><button type="button" className="dc-button dc-button--primary" disabled={mutation.busy || !nextStatus} onClick={transition}><FileClock size={14} /> Apply temporary revision transition</button></div></div> : <DocumentControlEmpty title="No temporary revision" message="Create a temporary revision against an existing source revision." />}
  </div>;
}

function ControlledCopyActions({ detail, tenant, onChanged }: Omit<Props, "activeView">) {
  const published = detail.revisions.find((revision) => revision.status === "PUBLISHED");
  const mutation = useMutation(onChanged);
  const [copyNumber, setCopyNumber] = useState("");
  const [location, setLocation] = useState("");
  const [holderName, setHolderName] = useState("");
  const [selectedId, setSelectedId] = useState(detail.controlled_copies[0]?.id || "");
  const selected = detail.controlled_copies.find((row) => row.id === selectedId) || detail.controlled_copies[0];
  const events = selected ? COPY_EVENTS[selected.status] || [] : [];
  const [eventType, setEventType] = useState(events[0] || "TRANSFER");
  const [holderId, setHolderId] = useState("");
  const [toLocation, setToLocation] = useState("");
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState("");

  const create = (event: FormEvent) => {
    event.preventDefault();
    if (!published) return;
    void mutation.run(() => createControlledCopy(tenant, { manual_id: detail.document.id, revision_id: published.id, copy_number: copyNumber, format: "HARDCOPY", holder_name: holderName || null, location_text: location, metadata: {} }));
  };
  const addEvent = () => {
    if (!selected) return;
    void mutation.run(() => createControlledCopyEvent(tenant, selected.id, { event_type: eventType, to_holder_user_id: holderId || null, to_location: toLocation || null, reason: reason.trim() || null, evidence: evidenceFrom(evidence) }));
  };

  return <div className="dc-grid">
    <form className="dc-form" onSubmit={create}><label><span>Copy number</span><input value={copyNumber} onChange={(event) => setCopyNumber(event.target.value)} required /></label><label><span>Holder name</span><input value={holderName} onChange={(event) => setHolderName(event.target.value)} /></label><label className="wide"><span>Physical location</span><input value={location} onChange={(event) => setLocation(event.target.value)} required /></label><ErrorMessage message={mutation.error || (!published ? "A published revision is required before issuing a controlled copy." : "")} /><div className="dc-form__actions"><button type="submit" className="dc-button" disabled={mutation.busy || !published}><Copy size={14} /> Issue controlled copy</button></div></form>
    {selected ? <div className="dc-form"><label className="wide"><span>Controlled copy</span><select value={selected.id} onChange={(event) => { setSelectedId(event.target.value); setEventType(""); }}>{detail.controlled_copies.map((row) => <option key={row.id} value={row.id}>{row.copy_number} · {row.status} · {row.location_text}</option>)}</select></label><label><span>Custody event</span><select value={eventType} onChange={(event) => setEventType(event.target.value)}>{events.map((value) => <option key={value}>{value}</option>)}</select></label><label><span>New active tenant holder ID</span><input value={holderId} onChange={(event) => setHolderId(event.target.value)} /></label><label><span>New controlled location</span><input value={toLocation} onChange={(event) => setToLocation(event.target.value)} /></label><label className="wide"><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label><label className="wide"><span>Disposition evidence asset IDs</span><textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} /></label><div className="dc-form__actions"><button type="button" className="dc-button dc-button--primary" disabled={mutation.busy || !eventType} onClick={addEvent}><Archive size={14} /> Record custody event</button></div></div> : <DocumentControlEmpty title="No numbered copy" message="Issue a copy only from the effective published revision." />}
  </div>;
}

function ReviewActions({ detail, tenant, onChanged }: Omit<Props, "activeView">) {
  const mutation = useMutation(onChanged);
  const [dueAt, setDueAt] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const openReviews = useMemo(() => detail.reviews.filter((review) => review.status !== "COMPLETED"), [detail.reviews]);
  const [selectedId, setSelectedId] = useState(openReviews[0]?.id || "");
  const [outcome, setOutcome] = useState("CONTINUE");
  const [findingText, setFindingText] = useState("");
  const [actionText, setActionText] = useState("");

  const create = (event: FormEvent) => {
    event.preventDefault();
    void mutation.run(() => createDocumentReview(tenant, { manual_id: detail.document.id, revision_id: detail.document.current_published_revision_id || detail.document.latest_revision?.id || null, owner_user_id: ownerId || null, due_at: new Date(dueAt).toISOString() }));
  };
  const complete = () => {
    if (!selectedId) return;
    void mutation.run(() => completeDocumentReview(tenant, selectedId, { outcome, findings: idsFrom(findingText).map((value) => ({ finding: value })), actions: idsFrom(actionText).map((value) => ({ action: value })) }));
  };

  return <div className="dc-grid">
    <form className="dc-form" onSubmit={create}><label><span>Review due</span><input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} required /></label><label><span>Owner active tenant user ID</span><input value={ownerId} onChange={(event) => setOwnerId(event.target.value)} /></label><ErrorMessage message={mutation.error} /><div className="dc-form__actions"><button type="submit" className="dc-button" disabled={mutation.busy || !dueAt}><Plus size={14} /> Schedule review</button></div></form>
    {openReviews.length ? <div className="dc-form"><label className="wide"><span>Review to complete</span><select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>{openReviews.map((row) => <option key={row.id} value={row.id}>{row.due_at} · {row.owner_user_id || "Unassigned"} · {row.status}</option>)}</select></label><label><span>Outcome</span><select value={outcome} onChange={(event) => setOutcome(event.target.value)}><option>CONTINUE</option><option>CHANGE_REQUIRED</option><option>WITHDRAW</option><option>SUPERSEDE</option></select></label><label className="wide"><span>Findings</span><textarea value={findingText} onChange={(event) => setFindingText(event.target.value)} placeholder="Separate findings with commas, semicolons, or new lines" /></label><label className="wide"><span>Resulting actions</span><textarea value={actionText} onChange={(event) => setActionText(event.target.value)} placeholder="Separate actions with commas, semicolons, or new lines" /></label><div className="dc-form__actions"><button type="button" className="dc-button dc-button--primary" disabled={mutation.busy} onClick={complete}><CheckCircle2 size={14} /> Complete periodic review</button></div></div> : <DocumentControlEmpty title="No open review" message="Schedule the next periodic applicability review." />}
  </div>;
}
