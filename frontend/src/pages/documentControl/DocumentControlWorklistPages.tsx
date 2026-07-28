import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Archive,
  Boxes,
  ClipboardCheck,
  ClipboardList,
  Copy,
  FileClock,
  FileDiff,
  FileSearch,
  GitPullRequestArrow,
  Landmark,
  Link2,
  Search,
  Send,
  Settings,
} from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";

import {
  getDocumentControlDashboard,
  getDocumentControlDocument,
  getMasterRegisterReport,
  getOverdueDocumentControlReport,
  listAuthoritySubmissions,
  listControlledCopies,
  listDistributionCampaigns,
  listDocumentChangeRequests,
  listDocumentControlDocuments,
  listDocumentReviews,
  listDocumentWorkflows,
  listExternalSources,
  listIntegrationLinks,
  listTemporaryRevisions,
  type AuthoritySubmission,
  type ControlledCopy,
  type DistributionCampaign,
  type DocumentChangeRequest,
  type DocumentLibraryItem,
  type DocumentReviewPlan,
  type DocumentWorkflow,
  type ExternalSource,
  type IntegrationLink,
  type TemporaryRevision,
} from "../../services/documentControl";
import {
  getArchiveRegister,
  getDocumentControlSettings,
  getListOfEffectivePages,
  updateDocumentControlSettings,
  type ArchiveRegister,
  type DocumentControlSettings,
  type ListOfEffectivePages,
} from "../../services/documentControlReports";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlSection,
  DocumentControlStatus,
  useDocumentControlRoute,
} from "./DocumentControlShell";

function statusKind(status?: string | null): "success" | "warning" | "danger" | "info" | "neutral" {
  const value = String(status || "").toUpperCase();
  if (["PUBLISHED", "APPROVED", "COMPLETED", "ACKNOWLEDGED", "CURRENT", "READY", "IN_FORCE", "ISSUED"].includes(value)) return "success";
  if (["REJECTED", "EXPIRED", "WITHDRAWN", "ARCHIVED", "SUPERSEDED", "BLOCKED", "OVERDUE", "DESTROYED"].includes(value)) return "danger";
  if (["DRAFT", "PENDING", "OPEN", "IN_REVIEW", "CORRECTIONS_REQUIRED", "QUERY_RECEIVED", "SCHEDULED"].includes(value)) return "warning";
  return "info";
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function LiveWorklist<T>({
  title,
  subtitle,
  icon: Icon,
  load,
  headers,
  rows,
  emptyTitle,
  emptyMessage,
  onRow,
}: {
  title: string;
  subtitle: string;
  icon: typeof Search;
  load: () => Promise<T[]>;
  headers: string[];
  rows: (item: T) => ReactNode[];
  emptyTitle: string;
  emptyMessage: string;
  onRow?: (item: T) => void;
}) {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try { setItems(await load()); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "The worklist could not be loaded."); }
    finally { setLoading(false); }
  }, [load]);
  useEffect(() => { void refresh(); }, [refresh]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((item) => JSON.stringify(item).toLowerCase().includes(needle));
  }, [items, query]);
  return <DocumentControlShell title={title} subtitle={subtitle} actions={<button type="button" className="dc-button" onClick={() => void refresh()}>Refresh</button>}>
    <div className="dc-toolbar"><label className="dc-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${title.toLowerCase()}`} /></label></div>
    {loading ? <DocumentControlLoading label={`Loading ${title.toLowerCase()}…`} /> : null}
    {error ? <DocumentControlError message={error} retry={() => void refresh()} /> : null}
    {!loading && !error && filtered.length ? <div className="dc-table-wrap"><table className="dc-table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{filtered.map((item, index) => <tr key={index} className={onRow ? "dc-row--clickable" : ""} onClick={() => onRow?.(item)}>{rows(item).map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div> : null}
    {!loading && !error && !filtered.length ? <DocumentControlEmpty icon={Icon} title={query ? "No matching record" : emptyTitle} message={query ? "Clear or change the search text." : emptyMessage} /> : null}
  </DocumentControlShell>;
}

export function DocumentControlChangeRequestsPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const load = useCallback(() => listDocumentChangeRequests(tenant), [tenant]);
  return <LiveWorklist<DocumentChangeRequest> title="Change Requests" subtitle="Real amendment triggers from QMS, regulation, safety, operations, training, and continuous improvement." icon={ClipboardList} load={load} headers={["Request", "Source", "Priority", "Status", "Owner", "Due"]} rows={(row) => [<><strong>{row.title}</strong><small>{row.description}</small></>, <><strong>{row.source_module}</strong><small>{row.source_entity_type || "Document"} {row.source_entity_id || ""}</small></>, <DocumentControlStatus status={row.priority} kind={statusKind(row.priority)} />, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />, row.owner?.name || "Unassigned", formatDate(row.due_at)]} emptyTitle="No change request" emptyMessage="No amendment trigger has been raised." onRow={(row) => navigate(`${basePath}/change-proposals/${row.id}`)} />;
}

export function DocumentControlChangeRequestDetailPage() {
  const { tenant, proposalId, basePath } = useDocumentControlRoute();
  const [row, setRow] = useState<DocumentChangeRequest | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { listDocumentChangeRequests(tenant).then((items) => setRow(items.find((item) => item.id === proposalId) || null)).finally(() => setLoading(false)); }, [proposalId, tenant]);
  if (loading) return <DocumentControlShell title="Change request" subtitle="Loading controlled change record"><DocumentControlLoading /></DocumentControlShell>;
  if (!row) return <DocumentControlShell title="Change request not found" subtitle="The requested controlled change does not exist."><DocumentControlEmpty title="No matching request" message="Return to the change register." /></DocumentControlShell>;
  return <Navigate to={`${basePath}/library/${row.manual_id}?view=changes`} replace />;
}

export function DocumentControlWorkflowPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const load = useCallback(() => listDocumentWorkflows(tenant), [tenant]);
  return <LiveWorklist<DocumentWorkflow> title="Revision Workflows" subtitle="Technical, Quality, accountable-manager, authority, effectivity, publication, supersession, and archive states." icon={GitPullRequestArrow} load={load} headers={["Revision", "State", "Authority", "Training", "QMS", "Distribution", "Blockers"]} rows={(row) => [<><strong>{row.revision_id}</strong><small>Workflow {row.id} · version {row.version}</small></>, <DocumentControlStatus status={row.state} kind={statusKind(row.state)} />, row.requires_authority ? "Required" : "Not required", row.training_readiness_status, row.qms_readiness_status, row.distribution_readiness_status, row.blockers?.length ? <DocumentControlStatus status={`${row.blockers.length} blocking`} kind="danger" /> : <DocumentControlStatus status="Ready" kind="success" />]} emptyTitle="No active revision workflow" emptyMessage="Start a workflow from an editable document revision." onRow={(row) => navigate(`${basePath}/library/${row.manual_id}?view=workflow`)} />;
}

export function DocumentControlWorkflowDetailPage() {
  const { tenant, draftId, basePath } = useDocumentControlRoute();
  const [row, setRow] = useState<DocumentWorkflow | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { listDocumentWorkflows(tenant).then((items) => setRow(items.find((item) => item.id === draftId || item.revision_id === draftId) || null)).finally(() => setLoading(false)); }, [draftId, tenant]);
  if (loading) return <DocumentControlShell title="Revision workflow" subtitle="Loading workflow"><DocumentControlLoading /></DocumentControlShell>;
  if (!row) return <DocumentControlShell title="Workflow not found" subtitle="The workflow identifier did not resolve."><DocumentControlEmpty title="No matching workflow" message="Return to the workflow register." /></DocumentControlShell>;
  return <Navigate to={`${basePath}/library/${row.manual_id}?view=workflow`} replace />;
}

export function DocumentControlAuthorityPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const load = useCallback(() => listAuthoritySubmissions(tenant), [tenant]);
  return <LiveWorklist<AuthoritySubmission> title="Authority Submissions" subtitle="Submission references, KCAA or other authority responses, evidence, due dates, and approval status." icon={Landmark} load={load} headers={["Authority", "Reference", "Revision", "Status", "Submitted", "Response due"]} rows={(row) => [row.authority_name, row.submission_reference, row.revision_id, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />, formatDate(row.submitted_at), formatDate(row.response_due_at)]} emptyTitle="No authority submission" emptyMessage="No document revision currently has an authority submission record." onRow={(row) => navigate(`${basePath}/library/${row.manual_id}?view=authority`)} />;
}

export function DocumentControlTemporaryRevisionPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const load = useCallback(() => listTemporaryRevisions(tenant), [tenant]);
  return <LiveWorklist<TemporaryRevision> title="Temporary Revisions" subtitle="Temporary amendment approval, distribution, effectivity, expiry, withdrawal, and permanent incorporation." icon={FileClock} load={load} headers={["TR", "Subject", "Effective", "Expiry", "Approval", "Status"]} rows={(row) => [<><strong>{row.tr_number}</strong><small>{row.id}</small></>, row.title, row.effective_date, row.expiry_date, <DocumentControlStatus status={row.approval_status} kind={statusKind(row.approval_status)} />, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />]} emptyTitle="No temporary revision" emptyMessage="No temporary revision is recorded for this tenant." onRow={(row) => navigate(`${basePath}/tr/${row.id}`)} />;
}

export function DocumentControlTemporaryRevisionDetailPage() {
  const { tenant, trId, basePath } = useDocumentControlRoute();
  const [row, setRow] = useState<TemporaryRevision | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { listTemporaryRevisions(tenant).then((items) => setRow(items.find((item) => item.id === trId || item.tr_number === trId) || null)).finally(() => setLoading(false)); }, [tenant, trId]);
  if (loading) return <DocumentControlShell title="Temporary revision" subtitle="Loading controlled record"><DocumentControlLoading /></DocumentControlShell>;
  if (!row) return <DocumentControlShell title="Temporary revision not found" subtitle="The TR identifier did not resolve."><DocumentControlEmpty title="No matching TR" message="Return to the Temporary Revision register." /></DocumentControlShell>;
  return <Navigate to={`${basePath}/library/${row.manual_id}?view=temporary-revisions`} replace />;
}

export function DocumentControlDistributionPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const load = useCallback(() => listDistributionCampaigns(tenant), [tenant]);
  return <LiveWorklist<DistributionCampaign> title="Distribution and Acknowledgements" subtitle="Issue controlled revisions to active tenant recipients and retain read-and-understand evidence." icon={Send} load={load} headers={["Campaign", "Revision", "Status", "Issued", "Due", "Recipients"]} rows={(row) => [<><strong>{row.title}</strong><small>{row.id}</small></>, row.revision_id, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />, formatDate(row.issued_at), formatDate(row.due_at), Object.entries(row.recipients || {}).map(([key, value]) => `${key}: ${value}`).join(" · ") || "0"]} emptyTitle="No distribution campaign" emptyMessage="No revision or temporary revision has been prepared for controlled distribution." onRow={(row) => navigate(`${basePath}/distribution/${row.id}`)} />;
}

export function DocumentControlDistributionDetailPage() {
  const { tenant, eventId, basePath } = useDocumentControlRoute();
  const [row, setRow] = useState<DistributionCampaign | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { listDistributionCampaigns(tenant).then((items) => setRow(items.find((item) => item.id === eventId) || null)).finally(() => setLoading(false)); }, [eventId, tenant]);
  if (loading) return <DocumentControlShell title="Distribution campaign" subtitle="Loading campaign"><DocumentControlLoading /></DocumentControlShell>;
  if (!row) return <DocumentControlShell title="Campaign not found" subtitle="The distribution identifier did not resolve."><DocumentControlEmpty title="No matching campaign" message="Return to the distribution register." /></DocumentControlShell>;
  return <Navigate to={`${basePath}/library/${row.manual_id}?view=distribution`} replace />;
}

export function DocumentControlReviewPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const load = useCallback(() => listDocumentReviews(tenant), [tenant]);
  return <LiveWorklist<DocumentReviewPlan> title="Periodic Review Programme" subtitle="Review continued applicability, owner accountability, findings, outcomes, and resulting actions." icon={ClipboardCheck} load={load} headers={["Document", "Revision", "Owner", "Due", "Status", "Outcome"]} rows={(row) => [row.manual_id, row.revision_id || "Current", row.owner_user_id || "Unassigned", formatDate(row.due_at), <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />, row.outcome || "—"]} emptyTitle="No review scheduled" emptyMessage="No periodic review plan exists." onRow={(row) => navigate(`${basePath}/library/${row.manual_id}?view=reviews`)} />;
}

export function DocumentControlCopiesPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const load = useCallback(() => listControlledCopies(tenant), [tenant]);
  return <LiveWorklist<ControlledCopy> title="Controlled Copies" subtitle="Numbered hard-copy and offline-media custody, transfer, recall, return, withdrawal, and destruction." icon={Copy} load={load} headers={["Copy", "Document", "Revision", "Holder", "Location", "Status"]} rows={(row) => [row.copy_number, row.manual_id, row.revision_id, row.holder_name || row.holder_user_id || "Unassigned", row.location_text, <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />]} emptyTitle="No controlled copy" emptyMessage="No numbered copy has been issued." onRow={(row) => navigate(`${basePath}/library/${row.manual_id}?view=copies`)} />;
}

export function DocumentControlExternalSourcesPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const load = useCallback(() => listExternalSources(tenant), [tenant]);
  return <LiveWorklist<ExternalSource> title="External Technical Data" subtitle="OEM, authority, and supplier publication subscriptions, revision receipt, currency, and applicability." icon={Boxes} load={load} headers={["Provider", "Document", "Authority", "Update method", "Next currency check", "Status"]} rows={(row) => [row.provider, row.manual_id, row.authority || "—", row.update_method, formatDate(row.next_check_due_at), <DocumentControlStatus status={row.status} kind={statusKind(row.status)} />]} emptyTitle="No external source" emptyMessage="No external technical-data source is registered." onRow={(row) => navigate(`${basePath}/library/${row.manual_id}?view=external`)} />;
}

export function DocumentControlIntegrationsPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const load = useCallback(() => listIntegrationLinks(tenant), [tenant]);
  return <LiveWorklist<IntegrationLink> title="Cross-Module Integrations" subtitle="Canonical links to QMS, Training, Workforce, Planning, Production, Maintenance, Fleet, Stores, and Technical Records." icon={Link2} load={load} headers={["Module", "Entity", "Relation", "Document", "Status", "Blocking"]} rows={(row) => [row.source_module, `${row.entity_type} · ${row.entity_id}`, row.relation_type, row.manual_id, row.status_snapshot || "—", row.blocking ? <DocumentControlStatus status="Blocking" kind="danger" /> : "No"]} emptyTitle="No integration link" emptyMessage="No source-module record is linked to Document Control." onRow={(row) => navigate(`${basePath}/library/${row.manual_id}?view=integrations`)} />;
}

export function DocumentControlArchivePage() {
  const { tenant } = useDocumentControlRoute();
  const [register, setRegister] = useState<ArchiveRegister | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => { setLoading(true); setError(""); try { setRegister(await getArchiveRegister(tenant)); } catch (caught) { setError(caught instanceof Error ? caught.message : "Archive could not be loaded."); } finally { setLoading(false); } }, [tenant]);
  useEffect(() => { void load(); }, [load]);
  return <DocumentControlShell title="Archive and Withdrawal" subtitle="Superseded and archived revisions remain immutable, searchable, and linked to retention and disposition evidence.">{loading ? <DocumentControlLoading /> : null}{error ? <DocumentControlError message={error} retry={() => void load()} /> : null}{!loading && !error && register?.items.length ? <div className="dc-table-wrap"><table className="dc-table"><thead><tr><th>Document</th><th>Revision</th><th>Status</th><th>Superseded by</th><th>Archived</th><th>Retention</th><th>Disposition</th></tr></thead><tbody>{register.items.map((item, index) => { const revision = item.revision as Record<string, unknown>; const evidence = item.archive_evidence as Record<string, unknown> | null | undefined; return <tr key={String(revision.id || index)}><td><strong>{item.manual.code}</strong><small>{item.manual.title}</small></td><td>Issue {String(revision.issue_number || "—")} · Rev {String(revision.revision_number || "—")}</td><td><DocumentControlStatus status={String(revision.status || "ARCHIVED")} kind="danger" /></td><td>{item.superseded_by_revision_id || "—"}</td><td>{evidence?.archived_at ? formatDate(String(evidence.archived_at)) : "No legacy archive evidence"}</td><td>{String(evidence?.retention_until || "—")}</td><td>{String(evidence?.disposal_status || "Retained")}</td></tr>; })}</tbody></table></div> : null}{!loading && !error && !register?.items.length ? <DocumentControlEmpty icon={Archive} title="Archive is empty" message="Superseded and archived revisions will appear here automatically." /> : null}</DocumentControlShell>;
}

export function DocumentControlRegistersPage() {
  const { tenant } = useDocumentControlRoute();
  const [master, setMaster] = useState<Array<Record<string, unknown>>>([]);
  const [overdue, setOverdue] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => { setLoading(true); setError(""); try { const [masterResult, overdueResult] = await Promise.all([getMasterRegisterReport(tenant), getOverdueDocumentControlReport(tenant)]); setMaster(masterResult.items); setOverdue(overdueResult); } catch (caught) { setError(caught instanceof Error ? caught.message : "Reports could not be generated."); } finally { setLoading(false); } }, [tenant]);
  useEffect(() => { void load(); }, [load]);
  const overdueCounts = overdue ? Object.fromEntries(Object.entries(overdue).filter(([, value]) => Array.isArray(value)).map(([key, value]) => [key, (value as unknown[]).length])) : {};
  return <DocumentControlShell title="Registers and Reports" subtitle="Live reports generated from canonical document, revision, workflow, distribution, review, copy, and external-source records.">{loading ? <DocumentControlLoading /> : null}{error ? <DocumentControlError message={error} retry={() => void load()} /> : null}{!loading && !error ? <><section className="dc-metrics">{Object.entries(overdueCounts).map(([key, value]) => <div className={Number(value) ? "dc-metric dc-metric--danger" : "dc-metric"} key={key}><strong>{String(value)}</strong><span>{key.replaceAll("_", " ")}</span></div>)}</section><DocumentControlSection title="Master document register" description="Document identity, ownership, class, current source, effective revision, and review horizon.">{master.length ? <div className="dc-table-wrap" style={{ border: 0, borderRadius: 0 }}><table className="dc-table"><thead><tr><th>Code</th><th>Title</th><th>Class</th><th>Owner</th><th>Latest</th><th>Effective</th><th>Next review</th></tr></thead><tbody>{master.map((raw, index) => { const latest = (raw.latest_revision || {}) as Record<string, unknown>; const effective = (raw.effective_revision || {}) as Record<string, unknown>; return <tr key={String(raw.manual_id || index)}><td><strong>{String(raw.code || "—")}</strong></td><td>{String(raw.title || "—")}</td><td>{String(raw.document_class || "INTERNAL")}</td><td>{String(raw.owner_department || "—")}</td><td>{latest.id ? `Issue ${String(latest.issue_number || "—")} · Rev ${String(latest.revision_number || "—")}` : "No revision"}</td><td>{effective.id ? `Rev ${String(effective.revision_number || "—")}` : "No effective issue"}</td><td>{String(raw.next_review_due || "Not scheduled")}</td></tr>; })}</tbody></table></div> : <DocumentControlEmpty icon={FileSearch} title="Master register is empty" message="Register the first controlled document." />}</DocumentControlSection></> : null}</DocumentControlShell>;
}

export function DocumentControlSettingsPage() {
  const { tenant } = useDocumentControlRoute();
  const [settings, setSettings] = useState<DocumentControlSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { getDocumentControlSettings(tenant).then(setSettings).catch((caught) => setError(caught instanceof Error ? caught.message : "Settings could not be loaded.")).finally(() => setLoading(false)); }, [tenant]);
  const save = async () => { if (!settings) return; setSaving(true); setError(""); try { setSettings(await updateDocumentControlSettings(tenant, { default_retention_years: settings.default_retention_years, default_review_interval_months: settings.default_review_interval_months, regulated_workflow_enabled: settings.regulated_workflow_enabled, default_ack_required: settings.default_ack_required })); } catch (caught) { setError(caught instanceof Error ? caught.message : "Settings could not be saved."); } finally { setSaving(false); } };
  return <DocumentControlShell title="Document Control Settings" subtitle="Tenant defaults for retention, periodic review, regulated workflow, and acknowledgements." actions={<button type="button" className="dc-button dc-button--primary" disabled={!settings || saving} onClick={() => void save()}>{saving ? "Saving…" : "Save settings"}</button>}>{loading ? <DocumentControlLoading /> : null}{error ? <DocumentControlError message={error} /> : null}{settings ? <div className="dc-section"><form className="dc-form" onSubmit={(event) => { event.preventDefault(); void save(); }}><label><span>Default retention years</span><input type="number" min={1} max={100} value={settings.default_retention_years} onChange={(event) => setSettings({ ...settings, default_retention_years: Number(event.target.value) })} /></label><label><span>Default review interval months</span><input type="number" min={1} max={120} value={settings.default_review_interval_months} onChange={(event) => setSettings({ ...settings, default_review_interval_months: Number(event.target.value) })} /></label><label><span><input type="checkbox" checked={settings.regulated_workflow_enabled} onChange={(event) => setSettings({ ...settings, regulated_workflow_enabled: event.target.checked })} /> Enable regulated-workflow defaults</span></label><label><span><input type="checkbox" checked={settings.default_ack_required} onChange={(event) => setSettings({ ...settings, default_ack_required: event.target.checked })} /> Require acknowledgement by default</span></label></form></div> : null}</DocumentControlShell>;
}

export function DocumentControlRevisionPackagePage() {
  const { tenant, docId, basePath } = useDocumentControlRoute();
  const [documentId, setDocumentId] = useState<string | null>(null);
  useEffect(() => { listDocumentControlDocuments(tenant, { perPage: 100 }).then((result) => { const row = result.items.find((item) => item.id === docId || item.code.toLowerCase() === String(docId || "").toLowerCase()); setDocumentId(row?.id || null); }); }, [docId, tenant]);
  if (!documentId) return <DocumentControlShell title="Revision package" subtitle="Resolving document"><DocumentControlLoading /></DocumentControlShell>;
  return <Navigate to={`${basePath}/library/${documentId}?view=workflow`} replace />;
}

export function DocumentControlLEPPage() {
  const { tenant, docId, basePath } = useDocumentControlRoute();
  const [document, setDocument] = useState<DocumentLibraryItem | null>(null);
  const [lep, setLep] = useState<ListOfEffectivePages | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { (async () => { try { const library = await listDocumentControlDocuments(tenant, { perPage: 100 }); const row = library.items.find((item) => item.id === docId || item.code.toLowerCase() === String(docId || "").toLowerCase()); if (!row) throw new Error("Document not found"); setDocument(row); setLep(await getListOfEffectivePages(tenant, row.id)); } catch (caught) { setError(caught instanceof Error ? caught.message : "LEP could not be generated."); } finally { setLoading(false); } })(); }, [docId, tenant]);
  return <DocumentControlShell title="List of Effective Pages" subtitle="Generated from the selected immutable revision page map; the original source remains authoritative." actions={document ? <button type="button" className="dc-button" onClick={() => window.location.assign(`${basePath}/library/${document.id}?view=revisions`)}>Open document</button> : undefined}>{loading ? <DocumentControlLoading /> : null}{error ? <DocumentControlError message={error} /> : null}{lep?.warning ? <div className="dc-callout dc-callout--warning">{lep.warning}</div> : null}{lep?.rows.length ? <div className="dc-table-wrap"><table className="dc-table"><thead><tr><th>Page</th><th>Section</th><th>Issue</th><th>Revision</th><th>Effective date</th><th>Map source</th></tr></thead><tbody>{lep.rows.map((row) => <tr key={row.page_number}><td>{row.page_number}</td><td>{row.section || "Not mapped"}</td><td>{row.issue_number || "—"}</td><td>{row.revision_number || "—"}</td><td>{row.effective_date || "—"}</td><td>{row.source}</td></tr>)}</tbody></table></div> : null}</DocumentControlShell>;
}
