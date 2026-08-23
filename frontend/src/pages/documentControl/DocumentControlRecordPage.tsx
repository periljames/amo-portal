import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Archive,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  FileDiff,
  GitPullRequestArrow,
  History,
  Link2,
  Send,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  getDocumentControlDocument,
  type DocumentDetailResponse,
  type DocumentWorkflow,
} from "../../services/documentControl";
import {
  getDocumentGovernance,
  type GovernanceDetail,
} from "../../services/documentGovernance";
import { getDocumentRegulationLinks } from "../../services/documentControlReports";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlSection,
  DocumentControlStatus,
  useDocumentControlRoute,
} from "./DocumentControlShell";
import DocumentControlRecordActions, { type DocumentWorkspaceView } from "./DocumentControlRecordActions";
import "./dmsDocumentWorkspace.css";

const TABS: Array<[DocumentWorkspaceView, string, typeof BookOpen]> = [
  ["overview", "Overview", ShieldCheck],
  ["content", "Content", BookOpen],
  ["changes", "Changes", FileDiff],
  ["workflow", "Workflow", GitPullRequestArrow],
  ["distribution", "Distribution", Send],
  ["compliance", "Compliance", ClipboardCheck],
  ["relationships", "Relationships", Link2],
  ["history", "History", History],
];

const WORKFLOW_ORDER = [
  "DRAFT",
  "TECHNICAL_REVIEW",
  "TECHNICAL_APPROVED",
  "QUALITY_REVIEW",
  "QUALITY_APPROVED",
  "ACCOUNTABLE_MANAGER_APPROVAL",
  "AUTHORITY_SUBMITTED",
  "AUTHORITY_APPROVED",
  "SCHEDULED_FOR_EFFECTIVITY",
  "PUBLISHED",
] as const;

function statusKind(status?: string | null): "success" | "warning" | "danger" | "info" | "neutral" {
  const value = String(status || "").toUpperCase();
  if (["PUBLISHED", "APPROVED", "COMPLETED", "ACKNOWLEDGED", "CURRENT", "READY", "IN_FORCE", "CONFIRMED"].includes(value)) return "success";
  if (["REJECTED", "EXPIRED", "WITHDRAWN", "ARCHIVED", "SUPERSEDED", "BLOCKED", "OVERDUE", "CONFLICT", "FAILED"].includes(value)) return "danger";
  if (["DRAFT", "PENDING", "OPEN", "IN_REVIEW", "CORRECTIONS_REQUIRED", "QUERY_RECEIVED", "UNRESOLVED"].includes(value)) return "warning";
  if (["TECHNICAL_REVIEW", "QUALITY_REVIEW", "AUTHORITY_SUBMITTED", "SCHEDULED_FOR_EFFECTIVITY", "DETECTED"].includes(value)) return "info";
  return "neutral";
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function currentRevisionLabel(detail: DocumentDetailResponse): string {
  const revision = detail.document.latest_revision;
  if (!revision) return "No revision";
  return `${revision.issue_number ? `Issue ${revision.issue_number} · ` : ""}Rev ${revision.revision_number}`;
}

function activeTabFromParams(params: URLSearchParams): DocumentWorkspaceView {
  const requested = params.get("tab") || "overview";
  return TABS.some(([tab]) => tab === requested) ? requested as DocumentWorkspaceView : "overview";
}

export default function DocumentControlRecordPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { tenant, docId, basePath, readerBasePath } = useDocumentControlRoute();
  const [detail, setDetail] = useState<DocumentDetailResponse | null>(null);
  const [regulationLinks, setRegulationLinks] = useState<Array<Record<string, unknown>>>([]);
  const [governance, setGovernance] = useState<GovernanceDetail | null>(null);
  const [governanceLoading, setGovernanceLoading] = useState(false);
  const [governanceError, setGovernanceError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const activeView = activeTabFromParams(searchParams);

  const load = useCallback(async () => {
    if (!tenant || !docId) return;
    setLoading(true);
    setError("");
    try {
      const record = await getDocumentControlDocument(tenant, docId);
      setDetail(record);
      getDocumentRegulationLinks(tenant, docId).then(setRegulationLinks).catch(() => setRegulationLinks([]));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The document workspace could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [docId, tenant]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (activeView !== "relationships" || !tenant || !docId || governance || governanceLoading) return;
    let active = true;
    setGovernanceLoading(true);
    setGovernanceError("");
    getDocumentGovernance(tenant, docId)
      .then((result) => { if (active) setGovernance(result); })
      .catch((caught) => { if (active) setGovernanceError(caught instanceof Error ? caught.message : "Governed relationships could not be loaded."); })
      .finally(() => { if (active) setGovernanceLoading(false); });
    return () => { active = false; };
  }, [activeView, docId, governance, governanceLoading, tenant]);

  const document = detail?.document;
  const workflow = useMemo<DocumentWorkflow | null>(() => detail?.workflows[0] || null, [detail?.workflows]);
  const canControl = Boolean(detail?.capabilities.control);

  const selectTab = (tab: DocumentWorkspaceView) => {
    const next = new URLSearchParams(searchParams);
    next.delete("view");
    next.delete("governance");
    if (tab === "overview") next.delete("tab"); else next.set("tab", tab);
    setSearchParams(next);
  };

  const openReader = () => {
    if (!document?.read_target.revision_id) return;
    navigate(`${readerBasePath}/${document.id}/rev/${document.read_target.revision_id}/read`);
  };

  return (
    <DocumentControlShell
      title={document?.title || "Document workspace"}
      eyebrow={document?.code || "DOCUMENT CONTROL"}
      subtitle={document ? `${currentRevisionLabel(detail!)} · ${document.read_target.kind} · ${document.profile.owner_department}` : "Controlled document lifecycle workspace"}
      canControl={canControl}
      actions={document && detail ? <>
        <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library`)}>Back to library</button>
        <DocumentControlRecordActions detail={detail} onChanged={() => void load()} compact activeView={activeView} />
        <button type="button" className="dc-button dc-button--primary" disabled={!document.read_target.revision_id} onClick={openReader}><BookOpen size={15} /> Read current</button>
      </> : undefined}
    >
      {loading ? <DocumentControlLoading label="Loading unified document workspace…" /> : null}
      {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {!loading && !error && detail && document ? <div className="dms-document" data-testid="document-workspace">
        {document.read_target.kind === "UNCONTROLLED" ? <div className="dc-callout dc-callout--warning"><AlertTriangle size={18} /><div><strong>Uncontrolled revision.</strong> This content may be reviewed but is not approved for operational use or controlled distribution.</div></div> : null}

        <section className="dms-document__identity">
          <div className="dms-document__identity-main">
            <span className="dms-document__code">{document.code}</span>
            <div><h2>{document.title}</h2><p>{document.manual_type} · {document.profile.document_class.replaceAll("_", " ")}</p></div>
          </div>
          <div className="dms-document__identity-meta">
            <div><small>Current issue</small><strong>{currentRevisionLabel(detail)}</strong></div>
            <div><small>Effective</small><strong>{document.latest_revision?.effective_date || "Not effective"}</strong></div>
            <div><small>Status</small><DocumentControlStatus status={document.read_target.kind} kind={document.read_target.kind === "PUBLISHED" ? "success" : "warning"} /></div>
            <div><small>Workflow</small><DocumentControlStatus status={workflow?.state || "No active workflow"} kind={statusKind(workflow?.state)} /></div>
          </div>
        </section>

        <nav className="dms-document__tabs" aria-label="Document workspace">
          {TABS.map(([id, label, Icon]) => {
            const count = id === "content" ? detail.revisions.length
              : id === "changes" ? detail.changes.length + detail.temporary_revisions.length
              : id === "workflow" ? detail.workflows.length + detail.authority_submissions.length
              : id === "distribution" ? detail.distribution_campaigns.length + detail.controlled_copies.length
              : id === "compliance" ? detail.reviews.length + detail.external_sources.length + detail.applicability.length + regulationLinks.length
              : id === "relationships" ? detail.integrations.length + (governance?.relationships.length || 0)
              : id === "history" ? detail.history.length
              : null;
            return <button type="button" key={id} className={activeView === id ? "active" : ""} aria-current={activeView === id ? "page" : undefined} onClick={() => selectTab(id)}><Icon size={14} /><span>{label}</span>{count !== null && count > 0 ? <small>{count}</small> : null}</button>;
          })}
        </nav>

        {activeView === "overview" ? <OverviewView detail={detail} onOpenResponsibilities={() => navigate(`${basePath}/library/${document.id}?governance=assignments`)} /> : null}
        {activeView === "content" ? <ContentView detail={detail} readerBasePath={readerBasePath} /> : null}
        {activeView === "changes" ? <ChangesView detail={detail} /> : null}
        {activeView === "workflow" ? <WorkflowView detail={detail} /> : null}
        {activeView === "distribution" ? <DistributionView detail={detail} /> : null}
        {activeView === "compliance" ? <ComplianceView detail={detail} regulationLinks={regulationLinks} /> : null}
        {activeView === "relationships" ? <RelationshipsView detail={detail} governance={governance} loading={governanceLoading} error={governanceError} onRetry={() => { setGovernance(null); setGovernanceError(""); }} onOpenGovernance={() => navigate(`${basePath}/library/${document.id}?governance=assignments`)} /> : null}
        {activeView === "history" ? <HistoryView detail={detail} /> : null}

        {canControl ? <DocumentControlRecordActions detail={detail} onChanged={() => void load()} activeView={activeView} /> : null}
      </div> : null}
    </DocumentControlShell>
  );
}

function OverviewView({ detail, onOpenResponsibilities }: { detail: DocumentDetailResponse; onOpenResponsibilities: () => void }) {
  const { document } = detail;
  const workflow = detail.workflows[0];
  const currentIndex = workflow ? WORKFLOW_ORDER.indexOf(workflow.state as typeof WORKFLOW_ORDER[number]) : -1;
  const authorityRequired = Boolean(workflow?.requires_authority || document.profile.requires_authority_approval);
  const visualStages = WORKFLOW_ORDER.filter((stage) => authorityRequired || !["AUTHORITY_SUBMITTED", "AUTHORITY_APPROVED"].includes(stage));
  const blockers = workflow?.blockers || [];

  return <div className="dms-document__overview">
    <DocumentControlSection title="Lifecycle" description="The active controlled path from draft through publication.">
      {workflow ? <div className="dms-lifecycle" aria-label={`Current workflow state ${workflow.state}`}>{visualStages.map((stage) => {
        const stageIndex = WORKFLOW_ORDER.indexOf(stage);
        const complete = currentIndex > stageIndex || workflow.state === "PUBLISHED";
        const current = workflow.state === stage;
        return <div key={stage} className={complete ? "complete" : current ? "current" : "pending"}><span>{complete ? <CheckCircle2 size={14} /> : stageIndex + 1}</span><small>{stage.replaceAll("_", " ")}</small></div>;
      })}</div> : <DocumentControlEmpty icon={GitPullRequestArrow} title="No revision workflow is active" message="Start a controlled revision workflow only when a draft revision is ready to enter review." />}
      {workflow?.state === "CORRECTIONS_REQUIRED" ? <div className="dc-callout dc-callout--warning"><AlertTriangle size={17} /><div><strong>Corrections required.</strong> The revision must be corrected and resubmitted before review can continue.</div></div> : null}
    </DocumentControlSection>

    {blockers.length ? <DocumentControlSection title="Publication blockers" description="Resolve these conditions before the workflow can advance."><div className="dms-document__blockers">{blockers.map((blocker) => <article key={blocker.code}><AlertTriangle size={16} /><span><strong>{blocker.message}</strong><small>{blocker.code.replaceAll("_", " ")}</small></span></article>)}</div></DocumentControlSection> : null}

    <div className="dms-document__overview-grid">
      <DocumentControlSection title="Control status" description="High-value governance context for the current document.">
        <div className="dms-document__facts">
          <div><small>Owner department</small><strong>{document.profile.owner_department}</strong></div>
          <div><small>Criticality</small><strong>{document.profile.criticality}</strong></div>
          <div><small>Next review</small><strong>{document.profile.next_review_due || "Not scheduled"}</strong></div>
          <div><small>Acknowledgement</small><strong>{document.profile.acknowledgement_required ? "Required" : "Not required"}</strong></div>
          <div><small>Authority approval</small><strong>{document.profile.requires_authority_approval ? "Required" : "Not required"}</strong></div>
          <div><small>Access</small><strong>{document.profile.restricted_flag ? "Restricted" : "Permitted by role/scope"}</strong></div>
        </div>
      </DocumentControlSection>
      <DocumentControlSection title="Responsibilities" description="Named ownership and review authority remain explicit controlled assignments.">
        <div className="dms-document__responsibility-cta"><UsersRound size={22} /><div><strong>Review responsibility assignments</strong><p>Document owner, technical reviewer, Quality reviewer, approver, controller, custodian and retention roles.</p></div><button type="button" className="dc-button" onClick={onOpenResponsibilities}>Resolve assignments</button></div>
      </DocumentControlSection>
    </div>
  </div>;
}

function ContentView({ detail, readerBasePath }: { detail: DocumentDetailResponse; readerBasePath: string }) {
  const current = detail.document.latest_revision;
  return <div className="dms-document__stack">
    <DocumentControlSection title="Current controlled content" description="The source file remains the authoritative visual artifact.">
      {current ? <div className="dms-document__current-content"><FileDiff size={22} /><div><strong>{currentRevisionLabel(detail)}</strong><p>{current.source_filename || "Controlled source"} · {current.source_type || "Unknown format"} · {current.source_page_count || "—"} pages</p><small>{current.source_sha256 ? `SHA-256 ${current.source_sha256.slice(0, 20)}…` : "Checksum not available"}</small></div><a className="dc-button dc-button--primary" href={`${readerBasePath}/${detail.document.id}/rev/${current.id}/read`}><BookOpen size={14} /> Read</a></div> : <DocumentControlEmpty title="No source revision" message="Upload a controlled source revision before the document can enter lifecycle review." />}
    </DocumentControlSection>
    <SimpleTable title="Revision history" description="Immutable publication history and controlled draft revisions." empty="No revision history exists." headers={["Issue / revision", "Status", "Effective", "Source", "Integrity", "Action"]} rows={detail.revisions.map((revision) => [<><strong>Issue {revision.issue_number || "—"} · Rev {revision.revision_number}</strong><small>{revision.id}</small></>, <DocumentControlStatus status={revision.status} kind={statusKind(revision.status)} />, revision.effective_date || "—", <><strong>{revision.source_type || "—"}</strong><small>{revision.source_filename || "No source filename"}</small></>, <><strong>{revision.immutable ? "Immutable" : "Working revision"}</strong><small>{revision.source_sha256 ? `${revision.source_sha256.slice(0, 12)}…` : "No checksum"}</small></>, <a className="dc-button" href={`${readerBasePath}/${detail.document.id}/rev/${revision.id}/read`}><BookOpen size={14} /> Read</a>])} />
  </div>;
}

function ChangesView({ detail }: { detail: DocumentDetailResponse }) {
  return <div className="dms-document__stack">
    <SimpleTable title="Change requests" description="Controlled amendment triggers from Quality, regulation, safety, operations, training and improvement." empty="No change request is recorded." headers={["Request", "Source", "Priority", "Status", "Owner", "Due"]} rows={detail.changes.map((row) => [<><strong>{row.title}</strong><small>{row.description}</small></>, <><strong>{row.source_module}</strong><small>{row.source_entity_type || "Document"} {row.source_entity_id || ""}</small></>, <DocumentControlStatus status={row.priority} kind={statusKind(row.priority)} />, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />, row.owner?.name || "Unassigned", formatDate(row.due_at)])} />
    <SimpleTable title="Temporary revisions" description="Temporary controlled changes remain attached to their parent document and lifecycle." empty="No temporary revision is recorded." headers={["TR", "Subject", "Effective", "Expiry", "Approval", "Status"]} rows={detail.temporary_revisions.map((row) => [<><strong>{row.tr_number}</strong><small>{row.reason}</small></>, row.title, row.effective_date, row.expiry_date, <DocumentControlStatus status={row.approval_status} kind={statusKind(row.approval_status)} />, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />])} />
  </div>;
}

function WorkflowView({ detail }: { detail: DocumentDetailResponse }) {
  return <div className="dms-document__stack">
    <DocumentControlSection title="Approval workflow" description="Technical, Quality, management, authority and effectivity decisions remain one controlled lifecycle.">
      {detail.workflows.length ? <div className="dms-document__workflow-list">{detail.workflows.map((row) => <article key={row.id}><div><GitPullRequestArrow size={18} /><span><strong>{row.state.replaceAll("_", " ")}</strong><small>Revision {row.revision_id} · version {row.version}</small></span></div><div className="dms-document__workflow-readiness"><span>Training <b>{row.training_readiness_status}</b></span><span>QMS <b>{row.qms_readiness_status}</b></span><span>Distribution <b>{row.distribution_readiness_status}</b></span></div>{row.blockers?.length ? <div className="dms-document__workflow-blockers">{row.blockers.map((blocker) => <span key={blocker.code}><AlertTriangle size={13} /> {blocker.message}</span>)}</div> : <DocumentControlStatus status="Ready to advance" kind="success" />}</article>)}</div> : <DocumentControlEmpty icon={GitPullRequestArrow} title="No active workflow" message="No controlled revision is currently moving through review and approval." />}
    </DocumentControlSection>
    <SimpleTable title="Authority submissions" description="Authority evidence is shown in the same revision lifecycle rather than a separate register." empty="No authority submission is recorded." headers={["Authority", "Reference", "Revision", "Status", "Submitted", "Response due", "Evidence"]} rows={detail.authority_submissions.map((row) => [row.authority_name, <strong>{row.submission_reference}</strong>, row.revision_id, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />, formatDate(row.submitted_at), formatDate(row.response_due_at), `${row.evidence.length} item${row.evidence.length === 1 ? "" : "s"}`])} />
  </div>;
}

function DistributionView({ detail }: { detail: DocumentDetailResponse }) {
  return <div className="dms-document__stack">
    <SimpleTable title="Distribution campaigns" description="Current digital issue populations, acknowledgement obligations and retained issue evidence." empty="No distribution campaign is recorded." headers={["Campaign", "Revision", "Status", "Issued", "Due", "Recipients"]} rows={detail.distribution_campaigns.map((row) => [<><strong>{row.title}</strong><small>{row.id}</small></>, row.revision_id, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />, formatDate(row.issued_at), formatDate(row.due_at), Object.entries(row.recipients || {}).map(([key, value]) => `${key}: ${value}`).join(" · ") || "0"])} />
    <SimpleTable title="Physical controlled copies" description="Current custody state is explicit; event history remains retained evidence." empty="No numbered physical controlled copy exists." headers={["Copy", "Revision", "Holder", "Location", "Due back", "State"]} rows={detail.controlled_copies.map((row) => [<><strong>{row.copy_number}</strong><small>{row.format}</small></>, row.revision_id, row.holder_name || row.holder_user_id || "On shelf / unassigned", row.location_text, formatDate(row.due_back_at), <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />])} />
  </div>;
}

function ComplianceView({ detail, regulationLinks }: { detail: DocumentDetailResponse; regulationLinks: Array<Record<string, unknown>> }) {
  const regulationRows = regulationLinks.map((raw) => {
    const instrument = (raw.instrument || {}) as Record<string, unknown>;
    const requirement = (raw.requirement || {}) as Record<string, unknown>;
    return [String(instrument.authority || "—"), <><strong>{String(requirement.code || "—")}</strong><small>{String(requirement.text || "")}</small></>, String(raw.section || "Whole document"), String(raw.compliance_note || "—")];
  });
  return <div className="dms-document__stack">
    <SimpleTable title="Regulatory relationships" description="Requirements linked to this controlled document or section." empty="No regulatory mapping is recorded." headers={["Authority", "Requirement", "Section", "Compliance note"]} rows={regulationRows} />
    <SimpleTable title="Periodic reviews" description="Continued-applicability review programme and resulting outcomes." empty="No periodic review is scheduled." headers={["Due", "Owner", "Status", "Outcome", "Completed"]} rows={detail.reviews.map((row) => [formatDate(row.due_at), row.owner_user_id || "Unassigned", <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />, row.outcome || "—", formatDate(row.completed_at)])} />
    <SimpleTable title="External technical data" description="Provider, revision-currentness schedule and controlled external-source status." empty="No external technical-data source is registered." headers={["Provider", "Authority", "Method", "Last checked", "Next due", "Status"]} rows={detail.external_sources.map((row) => [row.provider, row.authority || "—", row.update_method, formatDate(row.last_checked_at), formatDate(row.next_check_due_at), <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />])} />
    <SimpleTable title="Applicability" description="Rules governing aircraft, component, base, department, role or other controlled effectivity." empty="No applicability rule is recorded." headers={["Rule", "Target type", "Target", "Effective", "Status"]} rows={detail.applicability.map((row) => [row.rule_type, row.target_type, row.target_value || row.target_id || "Criteria", `${row.effective_from || "Any"} → ${row.effective_to || "Open"}`, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />])} />
  </div>;
}

function RelationshipsView({ detail, governance, loading, error, onRetry, onOpenGovernance }: { detail: DocumentDetailResponse; governance: GovernanceDetail | null; loading: boolean; error: string; onRetry: () => void; onOpenGovernance: () => void }) {
  return <div className="dms-document__stack">
    <DocumentControlSection title="Governed relationships" description="Document-to-document and document-to-operational-record links preserve source ownership and permission boundaries." actions={<button type="button" className="dc-button" onClick={onOpenGovernance}><UsersRound size={14} /> Responsibilities & relationship review</button>}>
      {loading ? <DocumentControlLoading label="Loading governed relationships…" /> : null}
      {error ? <DocumentControlError message={error} retry={onRetry} /> : null}
      {!loading && !error && governance?.relationships.length ? <div className="dms-document__relationship-list">{governance.relationships.map((row) => <article key={row.id}><div><strong>{row.relationship_type.replaceAll("_", " ")}</strong><DocumentControlStatus status={row.resolution_status} kind={statusKind(row.resolution_status)} /></div><p>{row.target_manual ? `${row.target_manual.code} — ${row.target_manual.title}` : `${row.target_entity_type}${row.target_entity_id ? ` · ${row.target_entity_id}` : ""}`}</p>{row.exact_quote ? <small>“{row.exact_quote}”</small> : null}</article>)}</div> : null}
      {!loading && !error && governance && !governance.relationships.length ? <DocumentControlEmpty icon={Link2} title="No governed relationship" message="No confirmed or proposed document relationship is currently recorded." /> : null}
    </DocumentControlSection>
    <SimpleTable title="Cross-module links" description="Source modules keep ownership; DMS stores only governed identifiers, relationship and status evidence." empty="No cross-module link is recorded." headers={["Source module", "Entity", "Relationship", "Status", "Blocking"]} rows={detail.integrations.map((row) => [row.source_module, `${row.entity_type} · ${row.entity_id}`, row.relation_type, row.status_snapshot || "Not supplied", row.blocking ? <DocumentControlStatus status="Blocking" kind="danger" /> : "No"])} />
    {governance?.detected_references.length ? <SimpleTable title="Detected references requiring review" description="Machine-detected references stay proposals until authorized human review." empty="No detected reference." headers={["Reference", "Relationship", "Location", "Confidence", "Status"]} rows={governance.detected_references.map((row) => [row.normalized_token || row.raw_token, row.relationship_type, row.source_page_number ? `Page ${row.source_page_number}` : "Source location", `${row.confidence_percent}%`, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />])} /> : null}
  </div>;
}

function HistoryView({ detail }: { detail: DocumentDetailResponse }) {
  return <DocumentControlSection title="Controlled history" description="Append-only document and revision activity retained for audit traceability.">{detail.history.length ? <div className="dms-document__timeline">{detail.history.map((row) => <article key={row.id}><span><strong>{row.action.replaceAll("_", " ")}</strong><small>{row.entity_type} · {row.entity_id}{row.actor_id ? ` · actor ${row.actor_id}` : ""}</small></span><time>{formatDate(row.at)}</time></article>)}</div> : <DocumentControlEmpty icon={Archive} title="No audit activity" message="No controlled action is available in this document history." />}</DocumentControlSection>;
}

function SimpleTable({ title, description, empty, headers, rows }: { title: string; description: string; empty: string; headers: string[]; rows: ReactNode[][] }) {
  return <DocumentControlSection title={title} description={description} actions={rows.length ? <span className="dc-status">{rows.length}</span> : undefined}>{rows.length ? <div className="dc-table-wrap dms-document__table-wrap"><table className="dc-table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div> : <DocumentControlEmpty title={empty} message="No authoritative record exists for this section yet." />}</DocumentControlSection>;
}
