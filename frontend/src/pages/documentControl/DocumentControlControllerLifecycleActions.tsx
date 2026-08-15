import { useState, type FormEvent } from "react";
import { FileClock, Landmark, Play, Plus, ShieldCheck } from "lucide-react";

import {
  createAuthoritySubmission,
  createDocumentWorkflow,
  createTemporaryRevision,
  transitionDocumentWorkflow,
  type DocumentDetailResponse,
} from "../../services/documentControl";
import type { LifecycleView } from "./DocumentControlLifecycleActions";
import { DocumentControlEmpty } from "./DocumentControlShell";


type Props = {
  detail: DocumentDetailResponse;
  tenant: string;
  activeView: LifecycleView;
  onChanged: () => void;
};

type ControllerAction = { action: string; label: string; danger?: boolean };

const CONTROLLER_WORKFLOW_ACTIONS: Record<string, ControllerAction[]> = {
  DRAFT: [{ action: "SUBMIT_TECHNICAL_REVIEW", label: "Submit technical review" }],
  TECHNICAL_REVIEW: [{ action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true }],
  CORRECTIONS_REQUIRED: [{ action: "RESUBMIT_TECHNICAL_REVIEW", label: "Resubmit technical review" }],
  TECHNICAL_APPROVED: [{ action: "START_QUALITY_REVIEW", label: "Start Quality review" }],
  QUALITY_REVIEW: [{ action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true }],
  QUALITY_APPROVED: [{ action: "SUBMIT_ACCOUNTABLE_MANAGER", label: "Submit to Accountable Executive" }],
  ACCOUNTABLE_MANAGER_APPROVAL: [{ action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true }],
  AUTHORITY_SUBMITTED: [{ action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true }],
  SCHEDULED_FOR_EFFECTIVITY: [{ action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true }],
};

function statementsFrom(value: string): string[] {
  return value
    .split(/[\n;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
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
  return { busy, error, setError, run };
}

function ErrorMessage({ message }: { message: string }) {
  return message ? <div className="dc-form__error">{message}</div> : null;
}

function ApprovalBoundary() {
  return (
    <div className="dc-callout">
      <ShieldCheck size={17} />
      <div>
        <strong>Accountable approval is separate from document control.</strong>
        <div>Preparation and submission actions remain available. Approval, authority disposition, effectivity, publication, archive, and temporary-revision transitions require an authorized approver.</div>
      </div>
    </div>
  );
}

function ControllerWorkflowActions({ detail, tenant, onChanged }: Omit<Props, "activeView">) {
  const latest = detail.document.latest_revision;
  const workflow = detail.workflows[0];
  const mutation = useMutation(onChanged);
  const [comments, setComments] = useState("");

  if (!latest) {
    return <DocumentControlEmpty title="No revision exists" message="Upload a source revision before creating a controlled workflow." />;
  }
  if (!workflow) {
    return (
      <div className="dc-form">
        <ApprovalBoundary />
        <div className="dc-form__actions">
          <button
            type="button"
            className="dc-button dc-button--primary"
            disabled={mutation.busy || latest.immutable}
            onClick={() => void mutation.run(() => createDocumentWorkflow(tenant, {
              manual_id: detail.document.id,
              revision_id: latest.id,
            }))}
          >
            <Play size={14} /> Start revision workflow
          </button>
        </div>
        <ErrorMessage message={mutation.error} />
      </div>
    );
  }

  const actions = CONTROLLER_WORKFLOW_ACTIONS[workflow.state] || [];
  const transition = (item: ControllerAction) => {
    if (item.action === "REQUEST_CORRECTIONS" && !comments.trim()) {
      mutation.setError("Record the correction reason before returning the revision.");
      return;
    }
    void mutation.run(() => transitionDocumentWorkflow(tenant, workflow.id, {
      action: item.action,
      comments: comments.trim() || null,
      evidence: [],
      expected_version: workflow.version,
    }));
  };

  return (
    <div className="dc-form">
      <ApprovalBoundary />
      <div className="dc-callout">
        <FileClock size={17} />
        <div><strong>{workflow.state.replaceAll("_", " ")}</strong><div>Version {workflow.version}. Decision-only actions are withheld from this controller account.</div></div>
      </div>
      <label className="wide"><span>Submission or correction reason</span><textarea value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Explain the submission or correction request." /></label>
      <ErrorMessage message={mutation.error} />
      {actions.length ? (
        <div className="dc-form__actions">
          {actions.map((item) => (
            <button
              type="button"
              key={item.action}
              className={`dc-button ${item.danger ? "dc-button--danger" : "dc-button--primary"}`}
              disabled={mutation.busy}
              onClick={() => transition(item)}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : (
        <DocumentControlEmpty title="Awaiting accountable decision" message="An authorized approver must complete the next controlled decision." />
      )}
    </div>
  );
}

function ControllerAuthorityActions({ detail, tenant, onChanged }: Omit<Props, "activeView">) {
  const revision = detail.document.latest_revision;
  const workflow = detail.workflows[0];
  const mutation = useMutation(onChanged);
  const [authorityName, setAuthorityName] = useState("Kenya Civil Aviation Authority");
  const [reference, setReference] = useState("");
  const [responseDue, setResponseDue] = useState("");

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
      evidence: [],
    }));
  };

  return (
    <div className="dc-grid">
      <form className="dc-form" onSubmit={create}>
        <ApprovalBoundary />
        <label><span>Authority</span><input value={authorityName} onChange={(event) => setAuthorityName(event.target.value)} required /></label>
        <label><span>Submission reference</span><input value={reference} onChange={(event) => setReference(event.target.value)} required /></label>
        <label><span>Response due</span><input type="datetime-local" value={responseDue} onChange={(event) => setResponseDue(event.target.value)} /></label>
        <ErrorMessage message={mutation.error} />
        <div className="dc-form__actions"><button type="submit" className="dc-button" disabled={mutation.busy || !revision}><Landmark size={14} /> Create draft submission</button></div>
      </form>
      <DocumentControlEmpty
        title="Authority decisions are approver-only"
        message="Controllers may prepare a draft submission. Submission, response, approval, rejection, withdrawal, and workflow alignment require accountable approval authority."
      />
    </div>
  );
}

function ControllerTemporaryRevisionActions({ detail, tenant, onChanged }: Omit<Props, "activeView">) {
  const publishedRevisionId = detail.document.current_published_revision_id;
  const latest = detail.document.latest_revision;
  const sourceRevisionId = latest && latest.id !== publishedRevisionId && !latest.immutable ? latest.id : "";
  const mutation = useMutation(onChanged);
  const [number, setNumber] = useState("");
  const [title, setTitle] = useState("");
  const [reason, setReason] = useState("");
  const [affectedSections, setAffectedSections] = useState("");
  const [filingInstructions, setFilingInstructions] = useState("");
  const [effective, setEffective] = useState("");
  const [expiry, setExpiry] = useState("");

  const create = (event: FormEvent) => {
    event.preventDefault();
    if (!publishedRevisionId || !sourceRevisionId) return;
    void mutation.run(() => createTemporaryRevision(tenant, {
      manual_id: detail.document.id,
      base_revision_id: publishedRevisionId,
      revision_id: sourceRevisionId,
      tr_number: number,
      title,
      reason,
      affected_sections: statementsFrom(affectedSections).map((section) => ({ section })),
      filing_instructions: filingInstructions,
      effective_date: effective,
      expiry_date: expiry,
    }));
  };

  const sourceError = !publishedRevisionId
    ? "A published revision is required before creating a temporary revision."
    : !sourceRevisionId
      ? "Upload an uncontrolled source revision containing the temporary amendment before creating the TR record."
      : "";

  return (
    <div className="dc-grid">
      <form className="dc-form" onSubmit={create}>
        <ApprovalBoundary />
        <label><span>TR number</span><input value={number} onChange={(event) => setNumber(event.target.value)} required /></label>
        <label><span>Effective date</span><input type="date" value={effective} onChange={(event) => setEffective(event.target.value)} required /></label>
        <label className="wide"><span>Subject</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
        <label className="wide"><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} required /></label>
        <label className="wide"><span>Affected sections or insertion points</span><textarea value={affectedSections} onChange={(event) => setAffectedSections(event.target.value)} placeholder="One section or insertion point per line" required /></label>
        <label className="wide"><span>Filing instructions</span><textarea value={filingInstructions} onChange={(event) => setFilingInstructions(event.target.value)} placeholder="State where and how the temporary revision must be filed and removed" required /></label>
        <label><span>Expiry or incorporation due</span><input type="date" value={expiry} onChange={(event) => setExpiry(event.target.value)} required /></label>
        <ErrorMessage message={mutation.error || sourceError} />
        <div className="dc-form__actions"><button type="submit" className="dc-button" disabled={mutation.busy || Boolean(sourceError)}><Plus size={14} /> Create temporary revision</button></div>
      </form>
      <DocumentControlEmpty
        title="Temporary-revision decisions are approver-only"
        message="Controllers may prepare a temporary revision record. Review, approval, effectivity, withdrawal, expiry, and incorporation transitions require accountable approval authority."
      />
    </div>
  );
}

export default function DocumentControlControllerLifecycleActions(props: Props) {
  if (props.activeView === "workflow") return <ControllerWorkflowActions detail={props.detail} tenant={props.tenant} onChanged={props.onChanged} />;
  if (props.activeView === "authority") return <ControllerAuthorityActions detail={props.detail} tenant={props.tenant} onChanged={props.onChanged} />;
  if (props.activeView === "temporary-revisions") return <ControllerTemporaryRevisionActions detail={props.detail} tenant={props.tenant} onChanged={props.onChanged} />;
  return <DocumentControlEmpty title="No controller action" message="This lifecycle area has no controller-only action." />;
}
