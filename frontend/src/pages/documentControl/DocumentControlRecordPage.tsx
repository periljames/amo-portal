import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Archive,
  BookOpen,
  Boxes,
  ClipboardCheck,
  ClipboardList,
  Copy,
  FileClock,
  FileDiff,
  GitPullRequestArrow,
  History,
  Landmark,
  Link2,
  ListChecks,
  ScrollText,
  Send,
  ShieldCheck,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  getDocumentControlDocument,
  type DocumentDetailResponse,
  type DocumentWorkflow,
} from "../../services/documentControl";
import { getDocumentRegulationLinks } from "../../services/documentControlReports";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlSection,
  DocumentControlStatus,
  useDocumentControlRoute,
} from "./DocumentControlShell";
import DocumentControlRecordActions from "./DocumentControlRecordActions";

const VIEWS = [
  ["overview", "Overview", ScrollText],
  ["revisions", "Revisions", FileDiff],
  ["changes", "Changes", ClipboardList],
  ["workflow", "Workflow", GitPullRequestArrow],
  ["authority", "Authority", Landmark],
  ["temporary-revisions", "Temporary revisions", FileClock],
  ["distribution", "Distribution", Send],
  ["compliance", "Compliance", ShieldCheck],
  ["applicability", "Applicability", ListChecks],
  ["copies", "Controlled copies", Copy],
  ["reviews", "Reviews", ClipboardCheck],
  ["integrations", "Integrations", Link2],
  ["external", "External data", Boxes],
  ["history", "History", History],
] as const;

type ViewId = typeof VIEWS[number][0];

function statusKind(status?: string | null): "success" | "warning" | "danger" | "info" | "neutral" {
  const value = String(status || "").toUpperCase();
  if (["PUBLISHED", "APPROVED", "COMPLETED", "ACKNOWLEDGED", "CURRENT", "READY", "IN_FORCE"].includes(value)) return "success";
  if (["REJECTED", "EXPIRED", "WITHDRAWN", "ARCHIVED", "SUPERSEDED", "BLOCKED", "OVERDUE"].includes(value)) return "danger";
  if (["DRAFT", "PENDING", "OPEN", "IN_REVIEW", "CORRECTIONS_REQUIRED", "QUERY_RECEIVED"].includes(value)) return "warning";
  if (["TECHNICAL_REVIEW", "QUALITY_REVIEW", "AUTHORITY_SUBMITTED", "SCHEDULED_FOR_EFFECTIVITY"].includes(value)) return "info";
  return "neutral";
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function CountBadge({ value }: { value: number }) {
  return <span className="dc-status">{value}</span>;
}

export default function DocumentControlRecordPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { tenant, docId, basePath, readerBasePath } = useDocumentControlRoute();
  const [detail, setDetail] = useState<DocumentDetailResponse | null>(null);
  const [regulationLinks, setRegulationLinks] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestedView = searchParams.get("view") as ViewId | null;
  const activeView: ViewId = VIEWS.some(([id]) => id === requestedView) ? requestedView! : "overview";

  const load = useCallback(async () => {
    if (!tenant || !docId) return;
    setLoading(true);
    setError("");
    try {
      const record = await getDocumentControlDocument(tenant, docId);
      setDetail(record);
      getDocumentRegulationLinks(tenant, docId).then(setRegulationLinks).catch(() => setRegulationLinks([]));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The document record could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [docId, tenant]);

  useEffect(() => { void load(); }, [load]);

  const document = detail?.document;
  const workflow = useMemo<DocumentWorkflow | null>(() => detail?.workflows[0] || null, [detail?.workflows]);
  const canControl = Boolean(detail?.capabilities.control);
  const openReader = () => {
    if (!document?.read_target.revision_id) return;
    navigate(`${readerBasePath}/${document.id}/rev/${document.read_target.revision_id}/read`);
  };

  return (
    <DocumentControlShell
      title={document?.title || "Document record"}
      eyebrow={document?.code || "DOCUMENT CONTROL"}
      subtitle={document ? `${document.manual_type} · ${document.profile.document_class.replaceAll("_", " ")} · ${document.profile.owner_department}` : "Controlled document governance record"}
      canControl={canControl}
      actions={document ? (
        <>
          <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library`)}>Back to library</button>
          <button type="button" className="dc-button dc-button--primary" disabled={!document.read_target.revision_id} onClick={openReader}><BookOpen size={15} /> {document.read_target.label}</button>
        </>
      ) : undefined}
    >
      {loading ? <DocumentControlLoading label="Loading the complete document control record…" /> : null}
      {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {!loading && !error && detail && document ? (
        <>
          {document.read_target.kind === "UNCONTROLLED" ? (
            <div className="dc-callout dc-callout--warning"><AlertTriangle size={18} /><div><strong>Uncontrolled revision.</strong> This revision is available for authorized review but is not approved for operational use or controlled distribution.</div></div>
          ) : null}

          <section className="dc-record-header">
            <div>
              <h2>{document.title}</h2>
              <p>{document.code} · {document.manual_type} · owned by {document.profile.owner_department}</p>
              <div className="dc-record-meta">
                <DocumentControlStatus status={document.read_target.kind === "PUBLISHED" ? "Effective publication" : document.read_target.kind === "UNCONTROLLED" ? "Uncontrolled draft" : "No readable revision"} kind={document.read_target.kind === "PUBLISHED" ? "success" : document.read_target.kind === "UNCONTROLLED" ? "warning" : "danger"} />
                <DocumentControlStatus status={document.profile.document_class} kind="info" />
                {document.profile.regulated_flag ? <DocumentControlStatus status="Regulated" kind="warning" /> : null}
                {document.profile.restricted_flag ? <DocumentControlStatus status="Restricted" kind="danger" /> : null}
                {workflow ? <DocumentControlStatus status={workflow.state} kind={statusKind(workflow.state)} /> : null}
              </div>
            </div>
            <div className="dc-actions">
              {canControl ? <DocumentControlRecordActions detail={detail} onChanged={() => void load()} compact /> : null}
            </div>
          </section>

          <nav className="dc-record-tabs" aria-label="Document record views">
            {VIEWS.map(([id, label, Icon]) => {
              const count = id === "revisions" ? detail.revisions.length
                : id === "changes" ? detail.changes.length
                : id === "workflow" ? detail.workflows.length
                : id === "authority" ? detail.authority_submissions.length
                : id === "temporary-revisions" ? detail.temporary_revisions.length
                : id === "distribution" ? detail.distribution_campaigns.length
                : id === "applicability" ? detail.applicability.length
                : id === "copies" ? detail.controlled_copies.length
                : id === "reviews" ? detail.reviews.length
                : id === "integrations" ? detail.integrations.length
                : id === "external" ? detail.external_sources.length
                : id === "compliance" ? regulationLinks.length
                : id === "history" ? detail.history.length
                : null;
              return (
                <button type="button" key={id} className={activeView === id ? "active" : ""} onClick={() => setSearchParams({ view: id })}>
                  <Icon size={14} /> {label}{count !== null ? ` (${count})` : ""}
                </button>
              );
            })}
          </nav>

          {activeView === "overview" ? <OverviewView detail={detail} /> : null}
          {activeView === "revisions" ? <RevisionsView detail={detail} readerBasePath={readerBasePath} /> : null}
          {activeView === "changes" ? <ChangesView detail={detail} /> : null}
          {activeView === "workflow" ? <WorkflowView detail={detail} /> : null}
          {activeView === "authority" ? <AuthorityView detail={detail} /> : null}
          {activeView === "temporary-revisions" ? <TemporaryRevisionView detail={detail} /> : null}
          {activeView === "distribution" ? <DistributionView detail={detail} /> : null}
          {activeView === "compliance" ? <ComplianceView links={regulationLinks} /> : null}
          {activeView === "applicability" ? <ApplicabilityView detail={detail} /> : null}
          {activeView === "copies" ? <CopiesView detail={detail} /> : null}
          {activeView === "reviews" ? <ReviewsView detail={detail} /> : null}
          {activeView === "integrations" ? <IntegrationsView detail={detail} /> : null}
          {activeView === "external" ? <ExternalView detail={detail} /> : null}
          {activeView === "history" ? <HistoryView detail={detail} /> : null}

          {canControl ? <DocumentControlRecordActions detail={detail} onChanged={() => void load()} activeView={activeView} /> : null}
        </>
      ) : null}
    </DocumentControlShell>
  );
}

function OverviewView({ detail }: { detail: DocumentDetailResponse }) {
  const { document } = detail;
  return (
    <div className="dc-grid">
      <DocumentControlSection title="Control profile" description="Governance settings attached to the canonical document record.">
        <div className="dc-stat-list">
          <div><strong>{document.profile.document_class}</strong><span>Document class</span></div>
          <div><strong>{document.profile.owner_department}</strong><span>Owner department</span></div>
          <div><strong>{document.profile.language}</strong><span>Language</span></div>
          <div><strong>{document.profile.criticality}</strong><span>Criticality</span></div>
          <div><strong>{document.profile.review_interval_months} months</strong><span>Review interval</span></div>
          <div><strong>{document.profile.next_review_due || "Not scheduled"}</strong><span>Next review</span></div>
        </div>
      </DocumentControlSection>
      <DocumentControlSection title="Current revision" description="The original source remains the authoritative visual artifact.">
        {document.latest_revision ? (
          <div className="dc-stat-list">
            <div><strong>Issue {document.latest_revision.issue_number || "—"}</strong><span>Issue</span></div>
            <div><strong>Rev {document.latest_revision.revision_number}</strong><span>Revision</span></div>
            <div><strong>{document.latest_revision.status.replaceAll("_", " ")}</strong><span>Lifecycle status</span></div>
            <div><strong>{document.latest_revision.source_type || "—"}</strong><span>Source format</span></div>
            <div><strong>{document.latest_revision.source_page_count || "—"}</strong><span>Source pages</span></div>
            <div><strong>{document.latest_revision.effective_date || "Not effective"}</strong><span>Effective date</span></div>
          </div>
        ) : <DocumentControlEmpty title="No revision uploaded" message="Upload a PDF or DOCX revision before starting governance." />}
      </DocumentControlSection>
    </div>
  );
}

function RevisionsView({ detail, readerBasePath }: { detail: DocumentDetailResponse; readerBasePath: string }) {
  return (
    <DocumentControlSection title="Revision history" description="Revision IDs are immutable. Published revisions cannot be edited in place.">
      {detail.revisions.length ? (
        <div className="dc-table-wrap" style={{ border: 0, borderRadius: 0 }}><table className="dc-table"><thead><tr><th>Issue / revision</th><th>Status</th><th>Effective</th><th>Source</th><th>Integrity</th><th>Action</th></tr></thead><tbody>{detail.revisions.map((revision) => (
          <tr key={revision.id}>
            <td><strong>Issue {revision.issue_number || "—"} · Rev {revision.revision_number}</strong><small>{revision.id}</small></td>
            <td><DocumentControlStatus status={revision.status} kind={statusKind(revision.status)} /></td>
            <td>{revision.effective_date || "—"}<small>{revision.published_at ? `Published ${formatDate(revision.published_at)}` : "Not published"}</small></td>
            <td><strong>{revision.source_type || "—"}</strong><small>{revision.source_filename || "No source filename"}</small></td>
            <td><strong>{revision.immutable ? "Immutable" : "Editable workflow"}</strong><small>{revision.source_sha256 ? `${revision.source_sha256.slice(0, 12)}…` : "No checksum"}</small></td>
            <td><a className="dc-button" href={`${readerBasePath}/${detail.document.id}/rev/${revision.id}/read`}><BookOpen size={14} /> Read</a></td>
          </tr>
        ))}</tbody></table></div>
      ) : <DocumentControlEmpty title="No revisions" message="No source revision has been uploaded for this document." />}
    </DocumentControlSection>
  );
}

function ChangesView({ detail }: { detail: DocumentDetailResponse }) {
  return (
    <DocumentControlSection title="Change requests" description="Triggers may come from QMS, regulation, safety, operations, training, or continuous improvement.">
      {detail.changes.length ? <div className="dc-table-wrap" style={{ border: 0, borderRadius: 0 }}><table className="dc-table"><thead><tr><th>Request</th><th>Source</th><th>Priority</th><th>Status</th><th>Owner</th><th>Due</th></tr></thead><tbody>{detail.changes.map((row) => <tr key={row.id}><td><strong>{row.title}</strong><small>{row.description}</small></td><td><strong>{row.source_module}</strong><small>{row.source_entity_type || "Manual"} {row.source_entity_id || ""}</small></td><td><DocumentControlStatus status={row.priority} kind={row.priority === "CRITICAL" ? "danger" : row.priority === "HIGH" ? "warning" : "neutral"} /></td><td><DocumentControlStatus status={row.status} kind={statusKind(row.status)} /></td><td>{row.owner?.name || "Unassigned"}</td><td>{formatDate(row.due_at)}</td></tr>)}</tbody></table></div> : <DocumentControlEmpty title="No change request" message="No amendment trigger is recorded for this document." />}
    </DocumentControlSection>
  );
}

function WorkflowView({ detail }: { detail: DocumentDetailResponse }) {
  return (
    <DocumentControlSection title="Revision workflows" description="The server controls state transitions, blockers, authority requirements, and optimistic concurrency.">
      {detail.workflows.length ? <div className="dc-section__body dc-grid">{detail.workflows.map((row) => <article className="dc-card" key={row.id}><GitPullRequestArrow size={18} /><div><strong>{row.state.replaceAll("_", " ")}</strong><p>Revision {row.revision_id} · version {row.version}</p><p>Training: {row.training_readiness_status} · QMS: {row.qms_readiness_status} · Distribution: {row.distribution_readiness_status}</p>{row.blockers?.length ? <p style={{ color: "#b91c1c" }}>{row.blockers.map((blocker) => blocker.message).join(" ")}</p> : <p>No active publication blocker.</p>}</div><DocumentControlStatus status={row.state} kind={statusKind(row.state)} /></article>)}</div> : <DocumentControlEmpty title="No workflow" message="Create a workflow against an editable revision to begin controlled review and approval." />}
    </DocumentControlSection>
  );
}

function AuthorityView({ detail }: { detail: DocumentDetailResponse }) {
  return <SimpleTable title="Authority submissions" description="Authority correspondence and evidence remain linked to the immutable revision." empty="No authority submission exists." headers={["Authority", "Reference", "Revision", "Status", "Submitted", "Response due"]} rows={detail.authority_submissions.map((row) => [row.authority_name, row.submission_reference, row.revision_id, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />, formatDate(row.submitted_at), formatDate(row.response_due_at)])} />;
}

function TemporaryRevisionView({ detail }: { detail: DocumentDetailResponse }) {
  return <SimpleTable title="Temporary revisions" description="Effectivity, distribution, expiry, and incorporation are controlled as first-class records." empty="No temporary revision exists." headers={["TR", "Subject", "Effective", "Expiry", "Approval", "Status"]} rows={detail.temporary_revisions.map((row) => [row.tr_number, row.title, row.effective_date, row.expiry_date, <DocumentControlStatus status={row.approval_status} kind={statusKind(row.approval_status)} />, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />])} />;
}

function DistributionView({ detail }: { detail: DocumentDetailResponse }) {
  return <SimpleTable title="Distribution campaigns" description="Recipients must be active, human tenant users. Acknowledgement status is stored per recipient." empty="No distribution campaign exists." headers={["Campaign", "Revision", "Status", "Issued", "Due", "Recipients"]} rows={detail.distribution_campaigns.map((row) => [row.title, row.revision_id, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />, formatDate(row.issued_at), formatDate(row.due_at), Object.entries(row.recipients || {}).map(([key, value]) => `${key}: ${value}`).join(" · ") || "0"])} />;
}

function ComplianceView({ links }: { links: Array<Record<string, unknown>> }) {
  return (
    <DocumentControlSection title="Regulatory requirement mapping" description="Requirements are linked to specific revisions and sections; the source instrument remains identifiable.">
      {links.length ? <div className="dc-table-wrap" style={{ border: 0, borderRadius: 0 }}><table className="dc-table"><thead><tr><th>Authority</th><th>Instrument</th><th>Requirement</th><th>Section</th><th>Compliance note</th></tr></thead><tbody>{links.map((raw, index) => {
        const instrument = (raw.instrument || {}) as Record<string, unknown>;
        const requirement = (raw.requirement || {}) as Record<string, unknown>;
        return <tr key={String(raw.id || index)}><td>{String(instrument.authority || "—")}</td><td><strong>{String(instrument.name || "—")}</strong><small>{String(instrument.version || "")}</small></td><td><strong>{String(requirement.code || "—")}</strong><small>{String(requirement.text || "")}</small></td><td>{String(raw.section || "Whole document")}</td><td>{String(raw.compliance_note || "—")}</td></tr>;
      })}</tbody></table></div> : <DocumentControlEmpty title="No regulatory mapping" message="No regulation requirement has been linked to this document revision or section." />}
    </DocumentControlSection>
  );
}

function ApplicabilityView({ detail }: { detail: DocumentDetailResponse }) {
  return <SimpleTable title="Applicability rules" description="Rules may target aircraft, serial ranges, components, bases, departments, roles, authorizations, or work records." empty="No applicability rule exists." headers={["Rule", "Target type", "Target", "Effective", "Status"]} rows={detail.applicability.map((row) => [row.rule_type, row.target_type, row.target_value || row.target_id || "Criteria", `${row.effective_from || "Any"} → ${row.effective_to || "Open"}`, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />])} />;
}

function CopiesView({ detail }: { detail: DocumentDetailResponse }) {
  return <SimpleTable title="Controlled copies" description="Numbered copy custody and every issue, transfer, recall, withdrawal, and destruction event are traceable." empty="No numbered controlled copy exists." headers={["Copy", "Revision", "Holder", "Location", "Status", "Issued"]} rows={detail.controlled_copies.map((row) => [row.copy_number, row.revision_id, row.holder_name || row.holder_user_id || "Unassigned", row.location_text, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />, formatDate(row.issued_at)])} />;
}

function ReviewsView({ detail }: { detail: DocumentDetailResponse }) {
  return <SimpleTable title="Periodic reviews" description="The review programme records continued applicability and resulting actions without fabricating future dates." empty="No periodic review is scheduled." headers={["Due", "Owner", "Status", "Outcome", "Completed"]} rows={detail.reviews.map((row) => [formatDate(row.due_at), row.owner_user_id || "Unassigned", <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />, row.outcome || "—", formatDate(row.completed_at)])} />;
}

function IntegrationsView({ detail }: { detail: DocumentDetailResponse }) {
  return <SimpleTable title="Cross-module links" description="Linked modules retain ownership of their records. Document Control stores only canonical IDs, relationship, blocker state, and a status snapshot." empty="No cross-module link exists." headers={["Module", "Entity", "Relation", "Status", "Blocking"]} rows={detail.integrations.map((row) => [row.source_module, `${row.entity_type} · ${row.entity_id}`, row.relation_type, row.status_snapshot || "Not supplied", row.blocking ? <DocumentControlStatus status="Blocking" kind="danger" /> : "No"])} />;
}

function ExternalView({ detail }: { detail: DocumentDetailResponse }) {
  return <SimpleTable title="External technical-data sources" description="Receipt, currency, subscription, provider, and applicability are controlled without rewriting the external publication." empty="No external source is registered." headers={["Provider", "Authority", "Method", "Last checked", "Next due", "Status"]} rows={detail.external_sources.map((row) => [row.provider, row.authority || "—", row.update_method, formatDate(row.last_checked_at), formatDate(row.next_check_due_at), <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />])} />;
}

function HistoryView({ detail }: { detail: DocumentDetailResponse }) {
  return (
    <DocumentControlSection title="Audit history" description="Append-only actions against the document and its revisions.">
      {detail.history.length ? <div className="dc-timeline">{detail.history.map((row) => <article key={row.id}><div><strong>{row.action.replaceAll("_", " ")}</strong><p>{row.entity_type} · {row.entity_id}{row.actor_id ? ` · actor ${row.actor_id}` : ""}</p></div><time>{formatDate(row.at)}</time></article>)}</div> : <DocumentControlEmpty icon={Archive} title="No audit event" message="No controlled action has yet been recorded against this document." />}
    </DocumentControlSection>
  );
}

function SimpleTable({ title, description, empty, headers, rows }: { title: string; description: string; empty: string; headers: string[]; rows: Array<Array<React.ReactNode>> }) {
  return (
    <DocumentControlSection title={title} description={description} actions={<CountBadge value={rows.length} />}>
      {rows.length ? <div className="dc-table-wrap" style={{ border: 0, borderRadius: 0 }}><table className="dc-table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div> : <DocumentControlEmpty title={empty} message="Use the control action below to create a real database record when required." />}
    </DocumentControlSection>
  );
}
