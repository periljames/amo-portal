import { useState, type FormEvent } from "react";
import { Landmark, Play, Plus, ShieldCheck } from "lucide-react";

import {
  createAuthoritySubmission,
  createDocumentWorkflow,
  transitionDocumentWorkflow,
  updateAuthoritySubmission,
  type DocumentDetailResponse,
} from "../../services/documentControl";
import type { DocumentEvidenceReference } from "../../services/documentControlEvidence";
import DocumentEvidencePicker from "./DocumentEvidencePicker";
import type { LifecycleView } from "./DocumentControlLifecycleActions";
import { DocumentControlEmpty } from "./DocumentControlShell";


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
  QUALITY_APPROVED: [{ action: "SUBMIT_ACCOUNTABLE_MANAGER", label: "Submit to Accountable Executive" }],
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

const DECISION_ACTIONS = new Set([
  "APPROVE_TECHNICAL",
  "APPROVE_QUALITY",
  "APPROVE_ACCOUNTABLE_MANAGER",
  "MARK_AUTHORITY_SUBMITTED",
  "MARK_AUTHORITY_APPROVED",
  "SCHEDULE_EFFECTIVITY",
  "PUBLISH",
  "ARCHIVE",
]);

const AUTHORITY_NEXT: Record<string, string[]> = {
  DRAFT: ["SUBMITTED", "WITHDRAWN"],
  SUBMITTED: ["IN_REVIEW", "QUERY_RECEIVED", "APPROVED", "REJECTED", "WITHDRAWN"],
  IN_REVIEW: ["QUERY_RECEIVED", "APPROVED", "REJECTED", "WITHDRAWN"],
  QUERY_RECEIVED: ["SUBMITTED", "IN_REVIEW", "APPROVED", "REJECTED", "WITHDRAWN"],
};

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
  return { busy, error, setError, run };
}

function ErrorMessage({ message }: { message: string }) {
  return message ? <div className="dc-form__error" role="alert">{message}</div> : null;
}

function ApproverWorkflowActions({ detail, tenant, onChanged }: Omit<Props, "activeView">) {
  const latest = detail.document.latest_revision;
  const workflow = detail.workflows[0];
  const mutation = useMutation(onChanged);
  const [comments, setComments] = useState("");
  const [evidence, setEvidence] = useState<DocumentEvidenceReference[]>([]);
  const [effectiveAt, setEffectiveAt] = useState("");
  const [training, setTraining] = useState(workflow?.training_readiness_status || "NOT_REQUIRED");
  const [qms, setQms] = useState(workflow?.qms_readiness_status || "NOT_REQUIRED");

  if (!latest) return <DocumentControlEmpty title="No revision exists" message="Upload a source revision before creating a controlled workflow." />;
  if (!workflow) {
    return <div className="dc-form">
      <div className="dc-callout"><Play size={17} /><div><strong>Start controlled review.</strong><div>Impact and readiness are derived from the profile, open changes and live module links for revision {latest.revision_number}.</div></div></div>
      <div className="dc-form__actions"><button type="button" className="dc-button dc-button--primary" disabled={mutation.busy || latest.immutable} onClick={() => void mutation.run(() => createDocumentWorkflow(tenant, { manual_id: detail.document.id, revision_id: latest.id }))}><Play size={14} /> Start revision workflow</button></div>
      <ErrorMessage message={mutation.error} />
    </div>;
  }

  let actions = WORKFLOW_ACTIONS[workflow.state] || [];
  if (workflow.state === "ACCOUNTABLE_MANAGER_APPROVAL") {
    actions = workflow.requires_authority
      ? [
          { action: "MARK_AUTHORITY_SUBMITTED", label: "Confirm authority submission" },
          { action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true },
        ]
      : [
          { action: "APPROVE_ACCOUNTABLE_MANAGER", label: "Approve and schedule" },
          { action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true },
        ];
  }

  const transition = (item: ActionOption) => {
    const comment = comments.trim();
    if ((DECISION_ACTIONS.has(item.action) || item.action === "REQUEST_CORRECTIONS") && !comment) {
      mutation.setError(item.action === "REQUEST_CORRECTIONS"
        ? "Record the correction reason before returning the revision."
        : "Record the basis for this controlled decision before continuing.");
      return;
    }
    if ((training === "WAIVED" || qms === "WAIVED") && !evidence.length) {
      mutation.setError("A readiness waiver requires at least one uploaded controlled evidence file.");
      return;
    }
    void mutation.run(() => transitionDocumentWorkflow(tenant, workflow.id, {
      action: item.action,
      comments: comment || null,
      evidence,
      expected_version: workflow.version,
      effective_at: effectiveAt ? new Date(effectiveAt).toISOString() : undefined,
      training_readiness_status: training !== workflow.training_readiness_status ? training : undefined,
      qms_readiness_status: qms !== workflow.qms_readiness_status ? qms : undefined,
    }));
  };

  return <div className="dc-form" data-testid="document-control-approver-workflow-actions">
    <div className="dc-callout"><ShieldCheck size={17} /><div><strong>{workflow.state.replaceAll("_", " ")}</strong><div>Version {workflow.version} · Distribution readiness: {workflow.distribution_readiness_status}</div></div></div>
    <label className="wide"><span>Decision comments or waiver reason</span><textarea value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Explain the decision, correction, waiver or release basis." /></label>
    <DocumentEvidencePicker
      tenant={tenant}
      manualId={detail.document.id}
      revisionId={workflow.revision_id}
      category="WORKFLOW"
      purpose={`WORKFLOW_${workflow.state}`}
      value={evidence}
      onChange={setEvidence}
      label="Supporting decision evidence"
      help="Upload or select retained supporting files. The DMS adds the reviewed revision checksum to controlled decisions on the server."
    />
    <label><span>Training readiness</span><select value={training} onChange={(event) => setTraining(event.target.value)}><option>NOT_REQUIRED</option><option>PENDING</option><option>BLOCKED</option><option>READY</option><option>WAIVED</option></select></label>
    <label><span>QMS readiness</span><select value={qms} onChange={(event) => setQms(event.target.value)}><option>NOT_REQUIRED</option><option>PENDING</option><option>BLOCKED</option><option>READY</option><option>WAIVED</option></select></label>
    <label><span>Scheduled effectivity</span><input type="datetime-local" value={effectiveAt} onChange={(event) => setEffectiveAt(event.target.value)} /></label>
    <label><span>Distribution readiness</span><input value={workflow.distribution_readiness_status} readOnly /><small>Established by issuing a real campaign; it cannot be marked ready here.</small></label>
    <ErrorMessage message={mutation.error} />
    <div className="dc-form__actions">{actions.map((item) => <button type="button" key={item.action} className={`dc-button ${item.danger ? "dc-button--danger" : "dc-button--primary"}`} disabled={mutation.busy} onClick={() => transition(item)}>{item.label}</button>)}</div>
  </div>;
}

function ApproverAuthorityActions({ detail, tenant, onChanged }: Omit<Props, "activeView">) {
  const revision = detail.document.latest_revision;
  const workflow = detail.workflows[0];
  const mutation = useMutation(onChanged);
  const [authorityName, setAuthorityName] = useState("Kenya Civil Aviation Authority");
  const [reference, setReference] = useState("");
  const [responseDue, setResponseDue] = useState("");
  const [draftEvidence, setDraftEvidence] = useState<DocumentEvidenceReference[]>([]);
  const [selectedId, setSelectedId] = useState(detail.authority_submissions[0]?.id || "");
  const selected = detail.authority_submissions.find((row) => row.id === selectedId) || detail.authority_submissions[0];
  const available = selected ? AUTHORITY_NEXT[selected.status] || [] : [];
  const [nextStatus, setNextStatus] = useState(available[0] || "SUBMITTED");
  const [summary, setSummary] = useState("");
  const [evidence, setEvidence] = useState<DocumentEvidenceReference[]>([]);

  const create = (event: FormEvent) => {
    event.preventDefault();
    if (!revision) return;
    void mutation.run(() => createAuthoritySubmission(tenant, {
      manual_id: detail.document.id,
      revision_id: revision.id,
      workflow_id: workflow?.id || null,
      authority_name: authorityName,
      submission_reference: reference,
      response_due_at: responseDue ? new Date(responseDue).toISOString() : null,
      evidence: draftEvidence,
    }));
  };

  const update = () => {
    if (!selected || !nextStatus) return;
    if (["SUBMITTED", "APPROVED"].includes(nextStatus) && !evidence.length && !(selected.evidence || []).length) {
      mutation.setError(`${nextStatus === "APPROVED" ? "Authority approval" : "Authority submission"} requires retained evidence.`);
      return;
    }
    if (["QUERY_RECEIVED", "APPROVED", "REJECTED", "WITHDRAWN"].includes(nextStatus) && !summary.trim()) {
      mutation.setError("Record the authority response, approval reference or disposition reason before continuing.");
      return;
    }
    void mutation.run(() => updateAuthoritySubmission(tenant, selected.id, {
      status: nextStatus,
      response_summary: summary.trim() || null,
      response_due_at: responseDue ? new Date(responseDue).toISOString() : null,
      evidence: evidence.length ? evidence : undefined,
    }));
  };

  const selectSubmission = (id: string) => {
    setSelectedId(id);
    const row = detail.authority_submissions.find((item) => item.id === id);
    setNextStatus(row ? (AUTHORITY_NEXT[row.status] || [])[0] || "" : "");
    setSummary("");
    setEvidence([]);
  };

  return <div className="dc-grid" data-testid="document-control-approver-authority-actions">
    <form className="dc-form" onSubmit={create}>
      <label><span>Authority</span><input value={authorityName} onChange={(event) => setAuthorityName(event.target.value)} required /></label>
      <label><span>Submission reference</span><input value={reference} onChange={(event) => setReference(event.target.value)} required /></label>
      <label><span>Response due</span><input type="datetime-local" value={responseDue} onChange={(event) => setResponseDue(event.target.value)} /></label>
      {revision ? <DocumentEvidencePicker tenant={tenant} manualId={detail.document.id} revisionId={revision.id} category="AUTHORITY" purpose="AUTHORITY_DRAFT" value={draftEvidence} onChange={setDraftEvidence} label="Draft submission evidence" /> : null}
      <ErrorMessage message={mutation.error} />
      <div className="dc-form__actions"><button type="submit" className="dc-button" disabled={mutation.busy || !revision}><Plus size={14} /> Create draft submission</button></div>
    </form>
    {selected ? <div className="dc-form">
      <label className="wide"><span>Submission to update</span><select value={selected.id} onChange={(event) => selectSubmission(event.target.value)}>{detail.authority_submissions.map((row) => <option key={row.id} value={row.id}>{row.authority_name} · {row.submission_reference} · {row.status}</option>)}</select></label>
      <label><span>Next authority status</span><select value={nextStatus} onChange={(event) => setNextStatus(event.target.value)}>{available.map((status) => <option key={status}>{status}</option>)}</select></label>
      <label className="wide"><span>Authority response, approval reference, or disposition reason</span><textarea value={summary} onChange={(event) => setSummary(event.target.value)} /></label>
      <DocumentEvidencePicker tenant={tenant} manualId={detail.document.id} revisionId={selected.revision_id} category="AUTHORITY" purpose={`AUTHORITY_${nextStatus || selected.status}`} value={evidence} onChange={setEvidence} label="Authority submission / response evidence" help="Attach the submitted package, authority correspondence, approval letter or other retained authority evidence." />
      <ErrorMessage message={mutation.error} />
      <div className="dc-form__actions"><button type="button" className="dc-button dc-button--primary" disabled={mutation.busy || !nextStatus} onClick={update}><Landmark size={14} /> Record authority status</button></div>
    </div> : <DocumentControlEmpty title="No authority submission" message="Create a draft submission record against the current revision." />}
  </div>;
}

export default function DocumentControlApproverLifecycleActions(props: Props) {
  if (props.activeView === "workflow") return <ApproverWorkflowActions detail={props.detail} tenant={props.tenant} onChanged={props.onChanged} />;
  if (props.activeView === "authority") return <ApproverAuthorityActions detail={props.detail} tenant={props.tenant} onChanged={props.onChanged} />;
  return <DocumentControlEmpty title="No approver action" message="This lifecycle area uses its dedicated governed action surface." />;
}
