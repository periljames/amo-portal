import { useState } from "react";
import { CheckCircle2, RotateCcw } from "lucide-react";

import {
  transitionDocumentWorkflow,
  type DocumentDetailResponse,
  type DocumentWorkflow,
} from "../../services/documentControl";
import { DocumentControlEmpty } from "./DocumentControlShell";


type ReviewWorkflow = DocumentWorkflow & { allowed_actions?: string[] };

type ReviewerAction = {
  action: string;
  label: string;
  danger?: boolean;
};

const REVIEWER_ACTIONS: Record<string, ReviewerAction> = {
  APPROVE_TECHNICAL: { action: "APPROVE_TECHNICAL", label: "Approve technical review" },
  APPROVE_QUALITY: { action: "APPROVE_QUALITY", label: "Approve Quality review" },
  APPROVE_ACCOUNTABLE_MANAGER: { action: "APPROVE_ACCOUNTABLE_MANAGER", label: "Approve for management" },
  REQUEST_CORRECTIONS: { action: "REQUEST_CORRECTIONS", label: "Return with comments", danger: true },
};

function evidenceFrom(value: string): Array<{ asset_id: string }> {
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((asset_id) => ({ asset_id }));
}

export default function DocumentControlReviewerLifecycleActions({
  detail,
  tenant,
  onChanged,
}: {
  detail: DocumentDetailResponse;
  tenant: string;
  onChanged: () => void;
}) {
  const workflow = detail.workflows[0] as ReviewWorkflow | undefined;
  const actions = (workflow?.allowed_actions || [])
    .map((action) => REVIEWER_ACTIONS[action])
    .filter((action): action is ReviewerAction => Boolean(action));
  const [comments, setComments] = useState("");
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!workflow) {
    return <DocumentControlEmpty title="No assigned review" message="No active document workflow requires a decision from this account." />;
  }

  if (!actions.length) {
    return <DocumentControlEmpty title="Awaiting another workflow role" message="This account can read the lifecycle evidence, but the current stage is assigned to another controlled responsibility." />;
  }

  const transition = async (item: ReviewerAction) => {
    const comment = comments.trim();
    const retainedEvidence = evidenceFrom(evidence);
    if (!comment) {
      setError(item.action === "REQUEST_CORRECTIONS"
        ? "Record the correction reason before returning the revision."
        : "Record the basis for the approval decision.");
      return;
    }
    if (item.action !== "REQUEST_CORRECTIONS" && !retainedEvidence.length) {
      setError("Add at least one retained evidence reference before approving this revision.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await transitionDocumentWorkflow(tenant, workflow.id, {
        action: item.action,
        comments: comment,
        evidence: retainedEvidence,
        expected_version: workflow.version,
      });
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The assigned review decision could not be recorded.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="dc-form" data-testid="assigned-reviewer-actions">
    <div className="dc-callout">
      <CheckCircle2 size={17} />
      <div>
        <strong>Assigned document decision</strong>
        <div>{workflow.state.replaceAll("_", " ")} · only actions authorized by the effective governed responsibility are shown.</div>
      </div>
    </div>
    <label className="wide"><span>Review comments</span><textarea value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Record the basis for the decision or correction request." /></label>
    <label className="wide"><span>Evidence asset IDs</span><textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} placeholder="Retained evidence references, one per line; required for approvals" /></label>
    {error ? <div className="dc-form__error">{error}</div> : null}
    <div className="dc-form__actions">
      {actions.map((item) => <button
        key={item.action}
        type="button"
        className={`dc-button ${item.danger ? "dc-button--danger" : "dc-button--primary"}`}
        disabled={busy}
        onClick={() => void transition(item)}
      >
        {item.danger ? <RotateCcw size={14} /> : <CheckCircle2 size={14} />}
        {item.label}
      </button>)}
    </div>
  </div>;
}
