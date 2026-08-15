import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  FileDiff,
  FileOutput,
  FileUp,
  GitPullRequestArrow,
  Landmark,
  Link2,
  Send,
  ShieldCheck,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getDocumentControlDocument,
  type DocumentDetailResponse,
  type DocumentWorkflow,
} from "../../services/documentControl";
import "./documentWorkflowGuide.css";

type GuideCapabilities = DocumentDetailResponse["capabilities"] & {
  review?: boolean;
  approve?: boolean;
  publish?: boolean;
  upload_revision?: boolean;
};

type GuideTab = "content" | "changes" | "workflow" | "distribution" | "compliance" | "relationships" | "history";

type PrimaryGuide = {
  eyebrow: string;
  title: string;
  description: string;
  label: string;
  tab: GuideTab;
  blocked?: boolean;
};

const REVIEW_STATES = new Set(["TECHNICAL_REVIEW", "QUALITY_REVIEW", "ACCOUNTABLE_MANAGER_APPROVAL", "AUTHORITY_SUBMITTED"]);

function human(value?: string | null): string {
  return String(value || "").replaceAll("_", " ").trim();
}

function readinessTone(value?: string | null): "good" | "warn" | "bad" | "neutral" {
  const status = String(value || "").toUpperCase();
  if (["READY", "NOT_REQUIRED", "WAIVED", "COMPLETE", "COMPLETED"].includes(status)) return "good";
  if (["BLOCKED", "FAILED", "OVERDUE"].includes(status)) return "bad";
  if (["PENDING", "OPEN", "IN_REVIEW"].includes(status)) return "warn";
  return "neutral";
}

function nextGuide(detail: DocumentDetailResponse): PrimaryGuide {
  const latest = detail.document.latest_revision;
  const workflow = detail.workflows[0];
  const blockers = workflow?.blockers || [];
  const pendingAcks = detail.document.pending_acknowledgements;

  if (!latest) {
    return {
      eyebrow: "Required input",
      title: "Upload the first controlled source",
      description: "A document cannot enter review until a source revision exists.",
      label: "Upload revision",
      tab: "content",
    };
  }

  if (!workflow && detail.document.read_target.kind === "PUBLISHED") {
    return {
      eyebrow: "Effective publication",
      title: "Read the current controlled issue",
      description: "This published revision is the controlled reading target. Lifecycle decisions remain with authorized Document Control users.",
      label: "Read current issue",
      tab: "content",
    };
  }

  if (!workflow) {
    return {
      eyebrow: "Next lifecycle step",
      title: "Start the revision workflow",
      description: `Revision ${latest.revision_number} exists but has not entered the controlled review path.`,
      label: "Start workflow",
      tab: "workflow",
    };
  }

  if (workflow.state === "CORRECTIONS_REQUIRED") {
    return {
      eyebrow: "Required correction",
      title: "Correct the source, then resubmit",
      description: "The current revision was returned for correction. Upload the corrected source before resubmitting it for review.",
      label: "Open revision inputs",
      tab: "content",
    };
  }

  if (workflow.state === "DRAFT") {
    return {
      eyebrow: "Next lifecycle step",
      title: "Submit for technical review",
      description: "The draft is registered and ready to enter the first controlled review stage.",
      label: "Submit technical review",
      tab: "workflow",
    };
  }

  if (workflow.state === "TECHNICAL_REVIEW") {
    return {
      eyebrow: "Decision required",
      title: "Complete technical review",
      description: "Record the review basis, retained evidence and the technical decision before the workflow can continue.",
      label: "Open technical review",
      tab: "workflow",
    };
  }

  if (workflow.state === "TECHNICAL_APPROVED") {
    return {
      eyebrow: "Next lifecycle step",
      title: "Start Quality review",
      description: "Technical review is complete. The revision now requires the governed Quality review stage.",
      label: "Start Quality review",
      tab: "workflow",
    };
  }

  if (workflow.state === "QUALITY_REVIEW") {
    return {
      eyebrow: "Decision required",
      title: "Complete Quality review",
      description: "Record the Quality decision and retained evidence before management approval.",
      label: "Open Quality review",
      tab: "workflow",
    };
  }

  if (workflow.state === "QUALITY_APPROVED") {
    return {
      eyebrow: "Next lifecycle step",
      title: "Submit to Accountable Executive",
      description: "Quality review is complete. Send the governed revision to the accountable approval stage.",
      label: "Submit to management",
      tab: "workflow",
    };
  }

  if (workflow.state === "ACCOUNTABLE_MANAGER_APPROVAL") {
    return {
      eyebrow: "Decision required",
      title: workflow.requires_authority ? "Complete management approval and authority submission" : "Complete Accountable Executive approval",
      description: workflow.requires_authority
        ? "The management decision must be recorded and the authority submission stage completed before effectivity can be scheduled."
        : "Record the accountable approval basis before the revision can be scheduled for effectivity.",
      label: "Open approval controls",
      tab: "workflow",
    };
  }

  if (workflow.state === "AUTHORITY_SUBMITTED") {
    return {
      eyebrow: "External decision pending",
      title: "Record the authority disposition",
      description: "Keep the submission reference, response, evidence and approval or rejection status attached to this revision.",
      label: "Open authority controls",
      tab: "workflow",
    };
  }

  if (workflow.state === "AUTHORITY_APPROVED") {
    return {
      eyebrow: "Next lifecycle step",
      title: "Schedule effectivity",
      description: "Authority approval is recorded. Set the controlled effective date and confirm readiness conditions.",
      label: "Schedule effectivity",
      tab: "workflow",
    };
  }

  if (workflow.state === "SCHEDULED_FOR_EFFECTIVITY" && blockers.length) {
    return {
      eyebrow: "Publication blocked",
      title: `Resolve ${blockers.length} publication blocker${blockers.length === 1 ? "" : "s"}`,
      description: blockers[0]?.message || "Readiness conditions must be resolved before publication.",
      label: "Resolve blockers",
      tab: "workflow",
      blocked: true,
    };
  }

  if (workflow.state === "SCHEDULED_FOR_EFFECTIVITY") {
    return {
      eyebrow: "Release ready",
      title: "Publish the approved revision",
      description: "All server-reported publication blockers are clear. Complete the controlled publication step.",
      label: "Publish revision",
      tab: "workflow",
    };
  }

  if (workflow.state === "PUBLISHED" && pendingAcks > 0) {
    return {
      eyebrow: "Post-publication control",
      title: `${pendingAcks} acknowledgement${pendingAcks === 1 ? "" : "s"} pending`,
      description: "Track distribution completion and retained read-and-understand evidence for the effective publication.",
      label: "Track distribution",
      tab: "distribution",
    };
  }

  if (workflow.state === "PUBLISHED") {
    return {
      eyebrow: "Effective publication",
      title: "Maintain continued compliance",
      description: "The revision is effective. Continue distribution, periodic review, applicability and controlled-copy monitoring.",
      label: "Open compliance controls",
      tab: "compliance",
    };
  }

  return {
    eyebrow: "Controlled lifecycle",
    title: human(workflow.state) || "Review current document status",
    description: "Open the workflow controls to complete the next server-authorized action.",
    label: "Open workflow",
    tab: "workflow",
  };
}

function ReadinessItem({ label, value }: { label: string; value?: string | null }) {
  const tone = readinessTone(value);
  return <span className={`dc-flow-guide__readiness dc-flow-guide__readiness--${tone}`}><small>{label}</small><strong>{human(value) || "Not set"}</strong></span>;
}

export default function DocumentWorkflowGuide({
  tenant,
  basePath,
  manualId,
  refreshKey,
}: {
  tenant: string;
  basePath: string;
  manualId: string;
  refreshKey?: object;
}) {
  const navigate = useNavigate();
  const [detail, setDetail] = useState<DocumentDetailResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void getDocumentControlDocument(tenant, manualId)
      .then((result) => {
        if (!active) return;
        setDetail(result);
        setError("");
      })
      .catch((caught) => {
        if (active) setError(caught instanceof Error ? caught.message : "Workflow guidance could not be loaded.");
      });
    return () => { active = false; };
  }, [manualId, refreshKey, tenant]);

  const primary = useMemo(() => detail ? nextGuide(detail) : null, [detail]);
  const workflow: DocumentWorkflow | undefined = detail?.workflows[0];
  const capabilities = (detail?.capabilities || {}) as GuideCapabilities;
  const canAct = Boolean(capabilities.control || capabilities.review || capabilities.approve || capabilities.publish || capabilities.upload_revision);
  const isPublishedReaderProjection = Boolean(detail && !workflow && detail.document.read_target.kind === "PUBLISHED");

  const open = (tab: GuideTab, focusActions = true) => {
    const query = tab === "history" ? "tab=history" : `tab=${tab}`;
    navigate(`${basePath}/library/${manualId}?${query}${focusActions ? "#document-control-record-actions" : ""}`);
  };

  if (error) {
    return <div className="dc-flow-guide dc-flow-guide--error" role="status"><AlertTriangle size={17} /><span><strong>Workflow guidance unavailable.</strong><small>{error}</small></span></div>;
  }
  if (!detail || !primary) return <div className="dc-flow-guide dc-flow-guide--loading" aria-hidden="true" />;

  const blockers = workflow?.blockers || [];
  const inputActions: Array<[string, GuideTab, typeof FileUp]> = [
    ["Revision", "content", FileUp],
    ["Change", "changes", FileDiff],
    ["Workflow", "workflow", GitPullRequestArrow],
    ["Authority", "workflow", Landmark],
    ["Distribution", "distribution", Send],
    ["Compliance", "compliance", ClipboardCheck],
    ["Relationship", "relationships", Link2],
  ];
  const outputActions: Array<[string, GuideTab]> = [
    ["Audit history", "history"],
    ["Distribution evidence", "distribution"],
    ["Compliance evidence", "compliance"],
  ];

  const stage = workflow?.state
    || (detail.document.read_target.kind === "PUBLISHED"
      ? "PUBLISHED"
      : detail.document.latest_revision
        ? "NOT_STARTED"
        : "NO_REVISION");

  return <section className={`dc-flow-guide ${primary.blocked ? "dc-flow-guide--blocked" : ""}`} data-testid="document-workflow-guide">
    <div className="dc-flow-guide__primary">
      <span className="dc-flow-guide__icon">{primary.blocked ? <AlertTriangle size={19} /> : <ShieldCheck size={19} />}</span>
      <div className="dc-flow-guide__copy">
        <small>{primary.eyebrow}</small>
        <strong>{primary.title}</strong>
        <p>{primary.description}</p>
      </div>
      <button type="button" className="dc-button dc-button--primary" disabled={!canAct && !isPublishedReaderProjection && primary.tab !== "distribution" && primary.tab !== "compliance"} onClick={() => open(primary.tab)} data-testid="document-next-action">
        {primary.label} <ArrowRight size={14} />
      </button>
    </div>

    <div className="dc-flow-guide__readiness-row" aria-label="Workflow readiness">
      <ReadinessItem label="Stage" value={stage} />
      <ReadinessItem label="Training" value={workflow?.training_readiness_status} />
      <ReadinessItem label="QMS" value={workflow?.qms_readiness_status} />
      <ReadinessItem label="Distribution" value={workflow?.distribution_readiness_status} />
      <span className={`dc-flow-guide__readiness ${blockers.length ? "dc-flow-guide__readiness--bad" : "dc-flow-guide__readiness--good"}`}><small>Blockers</small><strong>{blockers.length ? blockers.length : "Clear"}</strong></span>
    </div>

    {blockers.length ? <div className="dc-flow-guide__blockers"><AlertTriangle size={15} /><div>{blockers.slice(0, 3).map((blocker) => <span key={blocker.code}><strong>{blocker.message}</strong><small>{human(blocker.code)}</small></span>)}</div></div> : null}

    <div className="dc-flow-guide__launchers">
      <div className="dc-flow-guide__launcher-group">
        <span><FileUp size={14} /> Inputs & forms</span>
        <div>{inputActions.map(([label, tab, Icon]) => <button type="button" key={label} onClick={() => open(tab)}><Icon size={13} /> {label}</button>)}</div>
      </div>
      <div className="dc-flow-guide__launcher-group dc-flow-guide__launcher-group--outputs">
        <span><FileOutput size={14} /> Outputs & evidence</span>
        <div>{outputActions.map(([label, tab]) => <button type="button" key={label} onClick={() => open(tab, false)}>{label}</button>)}<button type="button" onClick={() => navigate(`${basePath}/reports`)}>Reports</button></div>
      </div>
    </div>

    {REVIEW_STATES.has(workflow?.state || "") && !canAct ? <div className="dc-flow-guide__notice"><CheckCircle2 size={15} /><span>The next controlled decision is assigned to an authorized reviewer or approver. You can still inspect the record and retained evidence.</span></div> : null}
  </section>;
}
