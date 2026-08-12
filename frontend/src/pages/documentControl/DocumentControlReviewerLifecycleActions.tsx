import { useState } from "react";
import { CheckCircle2, RotateCcw } from "lucide-react";

import {
  transitionDocumentWorkflow,
  type DocumentDetailResponse,
  type DocumentWorkflow,
} from "../../services/documentControl";
import type { DocumentEvidenceReference } from "../../services/documentControlEvidence";
import DocumentEvidencePicker from "./DocumentEvidencePicker";
import { DocumentControlEmpty } from "./DocumentControlShell";
import { buildReviewerDecisionEvidence } from "./reviewerDecisionEvidence";


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

const APPROVAL_ACTIONS = new Set([
  "APPROVE_TECHNICAL",
  "APPROVE_QUALITY",
  "APPROVE_ACCOUNTABLE_MANAGER",
]);

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
  const [evidence, setEvidence] = useState<DocumentEvidenceReference[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!workflow) {
    return <DocumentControlEmpty title="No assigned review" message="No active document workflow requires a decision from this account." />;
  }

  if (!actions.length) {
    return <DocumentControlEmpty title="Awaiting another workflow role" message="This account can read the lifecycle evidence, but the current stage is assigned to another controlled responsibility." />;
  }

  const reviewedRevision = detail.revisions.find((revision) => revision.id === workflow.revision_id);
  const retainsSourceChecksum = Boolean(reviewedRevision?.source_sha256?.trim());

  const transition = async (item: ReviewerAction) => {
    const decisionComments = comments.trim();
    const retainedEvidence = buildReviewerDecisionEvidence(detail, workflow, evidence);
    const isApproval = APPROVAL_ACTIONS.has(item.action);

    if (!decisionComments) {
      setError(isApproval
        ? "Record the basis for the approval decision before continuing."
        : "Record the correction reason before returning the revision.");
      return;
    }
    if (isApproval && !retainsSourceChecksum && !retainedEvidence.length) {
      setError("This revision has no retained source checksum. Upload supporting controlled evidence before approving.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      await transitionDocumentWorkflow(tenant, workflow.id, {
        action: item.action,
        comments: decisionComments,
        evidence: isApproval ? retainedEvidence : [],
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
    <label className="wide"><span>Review comments</span><textarea required value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Required: record the basis for the decision or correction request." /></label>
    <DocumentEvidencePicker
      tenant={tenant}
      manualId={detail.document.id}
      revisionId={workflow.revision_id}
      category="REVIEW"
      purpose={`REVIEW_${workflow.state}`}
      value={evidence}
      onChange={setEvidence}
      label="Supporting review evidence"
      help="Attach checklists, review sheets, correspondence or other retained files. The server independently records the exact reviewed revision checksum."
    />
    <div className="dc-form__hint">
      {retainsSourceChecksum
        ? "The reviewed revision ID and source checksum will be appended to the decision by the server."
        : "This revision has no retained source checksum; supporting controlled evidence is required before approval."}
    </div>
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
