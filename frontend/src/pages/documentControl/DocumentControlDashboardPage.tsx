import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Archive,
  BookOpen,
  Boxes,
  ClipboardCheck,
  ClipboardList,
  Copy,
  FileClock,
  GitPullRequestArrow,
  Landmark,
  Link2,
  Send,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getDocumentControlDashboard,
  listDocumentControlDocuments,
  type DocumentControlDashboard,
  type DocumentLibraryItem,
} from "../../services/documentControl";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlSection,
  DocumentControlStatus,
  useDocumentControlRoute,
} from "./DocumentControlShell";

function metricClass(value: number, danger = false): string {
  if (danger && value > 0) return "dc-metric dc-metric--danger";
  if (value > 0) return "dc-metric dc-metric--warning";
  return "dc-metric";
}

export default function DocumentControlDashboardPage() {
  const navigate = useNavigate();
  const { tenant, basePath, readerBasePath } = useDocumentControlRoute();
  const [dashboard, setDashboard] = useState<DocumentControlDashboard | null>(null);
  const [documents, setDocuments] = useState<DocumentLibraryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    setError("");
    try {
      const [summary, library] = await Promise.all([
        getDocumentControlDashboard(tenant),
        listDocumentControlDocuments(tenant, { perPage: 8 }),
      ]);
      setDashboard(summary);
      setDocuments(library.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Document Control could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [tenant]);

  useEffect(() => { void load(); }, [load]);

  const canControl = Boolean(dashboard?.capabilities.control);
  const openDocument = (document: DocumentLibraryItem) => {
    if (document.read_target.revision_id) {
      navigate(`${readerBasePath}/${document.id}/rev/${document.read_target.revision_id}/read`);
      return;
    }
    navigate(`${basePath}/library/${document.id}`);
  };

  return (
    <DocumentControlShell
      title={canControl ? "Control Desk" : "Document Library"}
      subtitle={canControl
        ? "Live document governance, approvals, authority actions, distribution, reviews, copy custody, and technical-data currency."
        : "Find the current permitted revision, continue reading, and complete assigned acknowledgements."}
      canControl={canControl}
      actions={<button type="button" className="dc-button dc-button--primary" onClick={() => navigate(`${basePath}/library`)}><BookOpen size={15} /> Open library</button>}
    >
      {loading ? <DocumentControlLoading /> : null}
      {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {!loading && !error && dashboard ? (
        <>
          <section className="dc-metrics" aria-label="Document Control status">
            <div className="dc-metric"><strong>{dashboard.metrics.document_records}</strong><span>Document records</span></div>
            <div className="dc-metric dc-metric--success"><strong>{dashboard.metrics.effective_publications}</strong><span>Effective publications</span></div>
            <div className={metricClass(dashboard.metrics.draft_revisions)}><strong>{dashboard.metrics.draft_revisions}</strong><span>Draft and review revisions</span></div>
            <div className={metricClass(dashboard.metrics.active_workflows)}><strong>{dashboard.metrics.active_workflows}</strong><span>Active revision workflows</span></div>
            <div className={metricClass(dashboard.metrics.authority_pending)}><strong>{dashboard.metrics.authority_pending}</strong><span>Authority submissions pending</span></div>
            <div className={metricClass(dashboard.metrics.overdue_acknowledgements, true)}><strong>{dashboard.metrics.overdue_acknowledgements}</strong><span>Overdue acknowledgements</span></div>
            <div className={metricClass(dashboard.metrics.temporary_revisions_expiring_30_days, true)}><strong>{dashboard.metrics.temporary_revisions_expiring_30_days}</strong><span>TRs expiring within 30 days</span></div>
            <div className={metricClass(dashboard.metrics.reviews_due_60_days)}><strong>{dashboard.metrics.reviews_due_60_days}</strong><span>Reviews due within 60 days</span></div>
          </section>

          {canControl ? (
            <DocumentControlSection title="Operational workspaces" description="Each workspace is backed by tenant data. Counts are not inferred from static examples.">
              <div className="dc-section__body dc-grid">
                <button type="button" className="dc-card" onClick={() => navigate(`${basePath}/change-proposals`)}><ClipboardList size={18} /><div><strong>Change requests</strong><p>Assess audit, regulatory, safety, operational, and improvement triggers.</p></div><em>{dashboard.metrics.open_change_requests} open</em></button>
                <button type="button" className="dc-card" onClick={() => navigate(`${basePath}/drafts`)}><GitPullRequestArrow size={18} /><div><strong>Revision workflows</strong><p>Technical review, Quality approval, accountable-manager and effectivity gates.</p></div><em>{dashboard.metrics.active_workflows} active</em></button>
                <button type="button" className="dc-card" onClick={() => navigate(`${basePath}/authority`)}><Landmark size={18} /><div><strong>Authority submissions</strong><p>KCAA or other authority submissions, responses, evidence, and approval state.</p></div><em>{dashboard.metrics.authority_pending} pending</em></button>
                <button type="button" className="dc-card" onClick={() => navigate(`${basePath}/tr`)}><FileClock size={18} /><div><strong>Temporary revisions</strong><p>Control effectivity, distribution, expiry, withdrawal, and incorporation.</p></div><em>{dashboard.metrics.temporary_revisions_in_force} in force</em></button>
                <button type="button" className="dc-card" onClick={() => navigate(`${basePath}/distribution`)}><Send size={18} /><div><strong>Distribution</strong><p>Target active tenant users and track read-and-understand evidence.</p></div><em>{dashboard.metrics.pending_acknowledgements} pending</em></button>
                <button type="button" className="dc-card" onClick={() => navigate(`${basePath}/reviews`)}><ClipboardCheck size={18} /><div><strong>Periodic reviews</strong><p>Track continued applicability, review findings, and resulting actions.</p></div><em>{dashboard.metrics.reviews_due_60_days} due</em></button>
                <button type="button" className="dc-card" onClick={() => navigate(`${basePath}/controlled-copies`)}><Copy size={18} /><div><strong>Controlled copies</strong><p>Issue, transfer, recall, return, withdraw, and destroy numbered copies.</p></div><em>{dashboard.metrics.issued_controlled_copies} issued</em></button>
                <button type="button" className="dc-card" onClick={() => navigate(`${basePath}/external-sources`)}><Boxes size={18} /><div><strong>External technical data</strong><p>Monitor OEM, authority, and supplier revision currency and applicability.</p></div><em>{dashboard.metrics.external_currency_checks_due} checks due</em></button>
                <button type="button" className="dc-card" onClick={() => navigate(`${basePath}/integrations`)}><Link2 size={18} /><div><strong>Module integrations</strong><p>Trace QMS, Training, Planning, Maintenance, Production, Fleet, Stores, and records links.</p></div><em>Canonical IDs</em></button>
                <button type="button" className="dc-card" onClick={() => navigate(`${basePath}/archive`)}><Archive size={18} /><div><strong>Archive and withdrawal</strong><p>Retain superseded revisions and controlled-copy disposition evidence.</p></div><em>Immutable</em></button>
              </div>
            </DocumentControlSection>
          ) : null}

          <DocumentControlSection title="Available documents" description="A draft is readable only to authorized controllers and reviewers and remains visibly uncontrolled." actions={<button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library`)}>View all</button>}>
            {documents.length ? (
              <div className="dc-table-wrap" style={{ border: 0, borderRadius: 0 }}>
                <table className="dc-table">
                  <thead><tr><th>Code</th><th>Document</th><th>Revision</th><th>Control state</th><th>Primary action</th></tr></thead>
                  <tbody>{documents.map((document) => (
                    <tr className="dc-row--clickable" key={document.id} onClick={() => openDocument(document)}>
                      <td><strong>{document.code}</strong><small>{document.profile.document_class}</small></td>
                      <td><strong>{document.title}</strong><small>{document.manual_type}</small></td>
                      <td><strong>{document.latest_revision ? `Issue ${document.latest_revision.issue_number || "—"} · Rev ${document.latest_revision.revision_number}` : "No revision"}</strong><small>{document.latest_revision?.source_type || "No source"}</small></td>
                      <td><DocumentControlStatus status={document.read_target.kind === "UNCONTROLLED" ? "Uncontrolled draft" : document.read_target.kind === "PUBLISHED" ? "Effective" : "No readable revision"} kind={document.read_target.kind === "PUBLISHED" ? "success" : document.read_target.kind === "UNCONTROLLED" ? "warning" : "danger"} /></td>
                      <td><span className="dc-button">{document.read_target.label}</span></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            ) : <DocumentControlEmpty icon={AlertTriangle} title="No document record exists" message="A controller must upload or register a document before it can be governed or read." />}
          </DocumentControlSection>

          {canControl ? (
            <DocumentControlSection title="Recent controlled activity" description="Append-only domain audit events for the active tenant.">
              {dashboard.recent_activity.length ? (
                <div className="dc-timeline">{dashboard.recent_activity.map((activity) => (
                  <article key={activity.id}><div><strong>{activity.action.replaceAll("_", " ")}</strong><p>{activity.entity_type} · {activity.entity_id}</p></div><time>{activity.at ? new Date(activity.at).toLocaleString() : "—"}</time></article>
                ))}</div>
              ) : <DocumentControlEmpty title="No activity recorded" message="The audit timeline will populate when controlled actions occur." />}
            </DocumentControlSection>
          ) : null}
        </>
      ) : null}
    </DocumentControlShell>
  );
}
