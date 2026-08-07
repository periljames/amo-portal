import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  FileClock,
  FileSearch,
  FolderTree,
  GitPullRequestArrow,
  Landmark,
  Link2,
  Send,
  ShieldCheck,
  UsersRound,
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
  DocumentControlStatus,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";

type ControllerMetrics = DocumentControlDashboard["metrics"] & {
  control_profiles_missing?: number;
  document_owners_unassigned?: number;
  review_dates_missing?: number;
  documents_without_effective_issue?: number;
  critical_acknowledgement_gaps?: number;
};

type PriorityItem = {
  key: string;
  title: string;
  detail: string;
  value: number;
  path: string;
  tone: "danger" | "warning" | "info";
  icon: typeof AlertTriangle;
};

function metricValue(value?: number): number {
  return Number.isFinite(value) ? Number(value) : 0;
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
  const metrics = (dashboard?.metrics || {}) as ControllerMetrics;
  const dueSoon = metricValue(metrics.reviews_due_60_days)
    + metricValue(metrics.temporary_revisions_expiring_30_days)
    + metricValue(metrics.external_currency_checks_due);

  const priorities = useMemo<PriorityItem[]>(() => {
    const items: PriorityItem[] = [
      {
        key: "overdue-acknowledgements",
        title: "Overdue acknowledgements",
        detail: "People have not completed required read-and-understand evidence by the due date.",
        value: metricValue(metrics.overdue_acknowledgements),
        path: "/distribution",
        tone: "danger",
        icon: UsersRound,
      },
      {
        key: "review-dates-missing",
        title: "Review dates not assigned",
        detail: "Controlled documents need a visible review cycle and due date.",
        value: metricValue(metrics.review_dates_missing),
        path: "/reviews",
        tone: "danger",
        icon: ClipboardCheck,
      },
      {
        key: "owners-unassigned",
        title: "Document owners not assigned",
        detail: "Ownership is required for review, change assessment, and continued suitability.",
        value: metricValue(metrics.document_owners_unassigned),
        path: "/structure",
        tone: "danger",
        icon: FolderTree,
      },
      {
        key: "profiles-missing",
        title: "Control profiles missing",
        detail: "Records exist without the governance metadata used for access, review, and release control.",
        value: metricValue(metrics.control_profiles_missing),
        path: "/structure",
        tone: "danger",
        icon: ShieldCheck,
      },
      {
        key: "critical-acknowledgement-gaps",
        title: "Critical documents without acknowledgement control",
        detail: "Critical documented information is not configured to retain recipient evidence.",
        value: metricValue(metrics.critical_acknowledgement_gaps),
        path: "/settings",
        tone: "danger",
        icon: Send,
      },
      {
        key: "reviews-due",
        title: "Periodic reviews due within 60 days",
        detail: "Confirm continued suitability, accuracy, applicability, and required actions.",
        value: metricValue(metrics.reviews_due_60_days),
        path: "/reviews",
        tone: "warning",
        icon: ClipboardCheck,
      },
      {
        key: "temporary-revisions",
        title: "Temporary revisions expiring within 30 days",
        detail: "Incorporate, extend with authority, or withdraw before the expiry date.",
        value: metricValue(metrics.temporary_revisions_expiring_30_days),
        path: "/tr",
        tone: "warning",
        icon: FileClock,
      },
      {
        key: "external-currency",
        title: "External-source currency checks due",
        detail: "Verify OEM, authority, and supplier publications remain current and applicable.",
        value: metricValue(metrics.external_currency_checks_due),
        path: "/external-sources",
        tone: "warning",
        icon: Link2,
      },
      {
        key: "authority-pending",
        title: "Authority submissions pending",
        detail: "Submission, query, response, or approval evidence remains open.",
        value: metricValue(metrics.authority_pending),
        path: "/authority",
        tone: "warning",
        icon: Landmark,
      },
      {
        key: "without-effective-issue",
        title: "Documents without an effective issue",
        detail: "The record has no current published revision available to operational users.",
        value: metricValue(metrics.documents_without_effective_issue),
        path: "/library",
        tone: "info",
        icon: BookOpen,
      },
    ];
    return items.filter((item) => item.value > 0);
  }, [metrics]);

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
        ? "A focused view of document currency, release blockers, assigned controls, and audit-ready evidence."
        : "Open the current permitted issue directly. Drafts and governance records remain restricted to authorized personnel."}
      canControl={canControl}
      actions={<button type="button" className="dc-button dc-button--primary" onClick={() => navigate(`${basePath}/library`)}><BookOpen size={15} /> Open library</button>}
    >
      {loading ? <DocumentControlLoading /> : null}
      {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {!loading && !error && dashboard ? (
        <>
          {canControl ? (
            <>
              <div className="dc-standard-note">
                <ShieldCheck size={18} />
                <div>
                  <strong>ISO 9001 documented-information controls</strong>
                  <span>Identification, approval before release, controlled availability, revision history, distribution evidence, review, retention, and disposition are connected in one workflow. This workspace supports conformity; it does not by itself constitute certification.</span>
                </div>
              </div>

              <section className="dc-control-summary" aria-label="Document Control health">
                <div><strong>{metricValue(metrics.effective_publications)}</strong><span>Effective publications</span><small>Current controlled issues available</small></div>
                <div><strong>{metricValue(metrics.active_workflows)}</strong><span>Active release workflows</span><small>Technical, Quality, authority, or effectivity gates</small></div>
                <div className={dueSoon > 0 ? "warning" : ""}><strong>{dueSoon}</strong><span>Controls due soon</span><small>Reviews, temporary revisions, and source checks</small></div>
                <div className={metricValue(metrics.overdue_acknowledgements) > 0 ? "danger" : ""}><strong>{metricValue(metrics.overdue_acknowledgements)}</strong><span>Overdue acknowledgements</span><small>Evidence requiring immediate follow-up</small></div>
              </section>

              <div className="dc-command-bar" aria-label="Document Control shortcuts">
                <button type="button" onClick={() => navigate(`${basePath}/library`)}><BookOpen size={15} /><span>Register or find a document</span></button>
                <button type="button" onClick={() => navigate(`${basePath}/change-proposals`)}><GitPullRequestArrow size={15} /><span>Open change register</span></button>
                <button type="button" onClick={() => navigate(`${basePath}/registers`)}><FileSearch size={15} /><span>Generate registers</span></button>
                <button type="button" onClick={() => navigate(`${basePath}/integrations`)}><Link2 size={15} /><span>Review QMS links</span></button>
              </div>

              <div className="dc-dashboard-grid">
                <section className="dc-dashboard-panel dc-dashboard-panel--priority">
                  <header><div><h2>Priority queue</h2><p>Only exceptions that require a controller decision or follow-up are shown.</p></div><span>{priorities.length} categories</span></header>
                  {priorities.length ? (
                    <div className="dc-priority-list">
                      {priorities.map((item) => {
                        const Icon = item.icon;
                        return (
                          <button type="button" key={item.key} className={`dc-priority-row dc-priority-row--${item.tone}`} onClick={() => navigate(`${basePath}${item.path}`)}>
                            <Icon size={17} />
                            <span><strong>{item.title}</strong><small>{item.detail}</small></span>
                            <em>{item.value}</em>
                            <ArrowRight size={15} />
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="dc-all-clear"><CheckCircle2 size={22} /><div><strong>No control exception is currently due</strong><span>Continue monitoring changes, external sources, reviews, and distribution evidence.</span></div></div>
                  )}
                </section>

                <section className="dc-dashboard-panel dc-dashboard-panel--evidence">
                  <header><div><h2>Evidence built into the portal</h2><p>Controls that go beyond storing documents in a shared library.</p></div></header>
                  <div className="dc-evidence-list">
                    <div><ShieldCheck size={16} /><span><strong>Controlled release</strong><small>Role-separated technical, Quality, management, and authority decisions.</small></span></div>
                    <div><Send size={16} /><span><strong>Targeted distribution</strong><small>Named recipients, due dates, acknowledgement status, and retained evidence.</small></span></div>
                    <div><GitPullRequestArrow size={16} /><span><strong>Change impact and blockers</strong><small>QMS, training, authority, and operational links can block publication.</small></span></div>
                    <div><ClipboardCheck size={16} /><span><strong>Review and currency</strong><small>Periodic reviews, external-source checks, temporary revision expiry, and ownership.</small></span></div>
                    <div><FileSearch size={16} /><span><strong>Audit-ready registers</strong><small>Master register, LEP, archive, revision history, and append-only activity.</small></span></div>
                  </div>
                </section>
              </div>
            </>
          ) : (
            <section className="dc-control-summary dc-control-summary--reader" aria-label="Document library status">
              <div><strong>{dashboard.metrics.effective_publications}</strong><span>Effective publications</span><small>Current issues available to you</small></div>
              <div><strong>{dashboard.metrics.document_records}</strong><span>Library records</span><small>Within your permitted access scope</small></div>
            </section>
          )}

          <section className="dc-dashboard-panel dc-dashboard-panel--table">
            <header>
              <div><h2>{canControl ? "Available documents" : "Current publications"}</h2><p>{canControl ? "Open the current issue or inspect the control record when governance work is required." : "Select a row to open the current effective issue in the controlled reader."}</p></div>
              <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library`)}>View all</button>
            </header>
            {documents.length ? (
              <div className="dc-table-wrap dc-table-wrap--flush">
                <table className="dc-table">
                  <thead><tr><th>Code</th><th>Document</th><th>Revision</th><th>Control state</th><th>Primary action</th></tr></thead>
                  <tbody>{documents.map((document) => (
                    <tr className="dc-row--clickable" key={document.id} onClick={() => openDocument(document)}>
                      <td><strong>{document.code}</strong><small>{document.profile.document_class}</small></td>
                      <td><strong>{document.title}</strong><small>{document.manual_type} · {document.profile.owner_department}</small></td>
                      <td><strong>{document.latest_revision ? `Issue ${document.latest_revision.issue_number || "—"} · Rev ${document.latest_revision.revision_number}` : "No revision"}</strong><small>{document.latest_revision?.effective_date || document.latest_revision?.source_type || "No source"}</small></td>
                      <td><DocumentControlStatus status={document.read_target.kind === "UNCONTROLLED" ? "Uncontrolled draft" : document.read_target.kind === "PUBLISHED" ? "Effective" : "No readable revision"} kind={document.read_target.kind === "PUBLISHED" ? "success" : document.read_target.kind === "UNCONTROLLED" ? "warning" : "danger"} /></td>
                      <td><span className="dc-button">{document.read_target.label}</span></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            ) : <DocumentControlEmpty icon={AlertTriangle} title="No document is available" message={canControl ? "Upload or register a document before it can be governed or read." : "No effective publication is currently assigned to your access scope."} />}
          </section>

          {canControl ? (
            <section className="dc-dashboard-panel dc-dashboard-panel--activity">
              <header><div><h2>Recent controlled activity</h2><p>Latest append-only actions for the active tenant.</p></div></header>
              {dashboard.recent_activity.length ? (
                <div className="dc-activity-list">{dashboard.recent_activity.slice(0, 6).map((activity) => (
                  <article key={activity.id}><span /><div><strong>{activity.action.replaceAll("_", " ")}</strong><small>{activity.entity_type} · {activity.entity_id}</small></div><time>{activity.at ? new Date(activity.at).toLocaleString() : "—"}</time></article>
                ))}</div>
              ) : <DocumentControlEmpty title="No activity recorded" message="The evidence timeline will populate when controlled actions occur." />}
            </section>
          ) : null}
        </>
      ) : null}
    </DocumentControlShell>
  );
}
