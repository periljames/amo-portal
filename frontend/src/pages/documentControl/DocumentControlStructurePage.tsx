import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Boxes,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  FileCheck2,
  FileCog,
  FileText,
  FolderTree,
  History,
  Link2,
  ListTree,
  Network,
  Pencil,
  RefreshCw,
  Search,
  Settings2,
  ShieldAlert,
  X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getDocumentationTree,
  getDocumentationNodeConnections,
  getReferenceMonitor,
  reconcileDocumentationTree,
  reindexDocumentationRevision,
  resolveDocumentationReference,
  updateDocumentationExecutionProfile,
  updateDocumentationNode,
  type DocumentationExecutionProfile,
  type DocumentationNodeConnections,
  type DocumentationTree,
  type DocumentationTreeNode,
  type DocumentationNodeType,
  type ReferenceMonitorResponse,
} from "../../services/documentation";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
  useDocumentControlRoute,
} from "./DocumentControlShell";
import "./documentControlStructure.css";

const NODE_LABELS: Record<DocumentationNodeType, string> = {
  ROOT: "Documented information",
  MANAGEMENT_SYSTEM: "Management system / group",
  MANUAL: "Manual",
  POLICY: "Policy",
  PROCEDURE: "Procedure",
  WORK_INSTRUCTION: "Work instruction",
  FORM: "Form",
  CHECKLIST: "Checklist",
  REGISTER: "Register",
  EXTERNAL_DOCUMENT: "External controlled document",
  RECORD_SERIES: "Record series",
};

const NODE_ICONS: Record<DocumentationNodeType, typeof FileText> = {
  ROOT: Network,
  MANAGEMENT_SYSTEM: Boxes,
  MANUAL: BookOpen,
  POLICY: ShieldAlert,
  PROCEDURE: FileCog,
  WORK_INSTRUCTION: FileText,
  FORM: FileCheck2,
  CHECKLIST: ClipboardCheck,
  REGISTER: ListTree,
  EXTERNAL_DOCUMENT: FileText,
  RECORD_SERIES: FolderTree,
};

function descendants(items: DocumentationTreeNode[], parentId: string | null): DocumentationTreeNode[] {
  return items
    .filter((item) => (item.parent_id || null) === parentId)
    .sort((a, b) => a.order_index - b.order_index || a.title.localeCompare(b.title));
}

function nodeStatus(node: DocumentationTreeNode): { label: string; kind: "success" | "warning" | "danger" | "neutral" | "info" } {
  if (!node.manual_id) return { label: NODE_LABELS[node.node_type], kind: "neutral" };
  if (node.document?.current_published_revision_id) return { label: "Effective", kind: "success" };
  if (node.document?.latest_revision_id) return { label: "Draft / uncontrolled", kind: "warning" };
  return { label: "No revision", kind: "danger" };
}

function executable(node: DocumentationTreeNode): boolean {
  return ["FORM", "CHECKLIST", "REGISTER"].includes(node.node_type);
}

type StructureMode = "TREE" | "LIST";
type WorkspaceTab = "STRUCTURE" | "REFERENCES";

export default function DocumentControlStructurePage() {
  const navigate = useNavigate();
  const { tenant, readerBasePath } = useDocumentControlRoute();
  const [tree, setTree] = useState<DocumentationTree | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [connections, setConnections] = useState<DocumentationNodeConnections | null>(null);
  const [connectionsLoading, setConnectionsLoading] = useState(false);
  const [connectionsError, setConnectionsError] = useState("");
  const [connectionsRevision, setConnectionsRevision] = useState(0);
  const [monitor, setMonitor] = useState<ReferenceMonitorResponse | null>(null);
  const [tab, setTab] = useState<WorkspaceTab>("STRUCTURE");
  const [mode, setMode] = useState<StructureMode>("TREE");
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editingNode, setEditingNode] = useState<DocumentationTreeNode | null>(null);
  const [executionNode, setExecutionNode] = useState<DocumentationTreeNode | null>(null);
  const [resolvingReference, setResolvingReference] = useState<ReferenceMonitorResponse["items"][number] | null>(null);

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    setError("");
    try {
      const structure = await getDocumentationTree(tenant);
      setTree(structure);
      setSelectedNodeId((current) => (
        current && structure.items.some((item) => item.id === current)
          ? current
          : structure.root_id || structure.items[0]?.id || null
      ));
      setConnectionsRevision((current) => current + 1);
      if (structure.capabilities.control) {
        setMonitor(await getReferenceMonitor(tenant).catch(() => null));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The documented-information structure could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [tenant]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!tenant || !selectedNodeId) {
      setConnections(null);
      return;
    }
    let active = true;
    setConnectionsLoading(true);
    setConnectionsError("");
    void getDocumentationNodeConnections(tenant, selectedNodeId)
      .then((result) => { if (active) setConnections(result); })
      .catch((caught) => {
        if (active) setConnectionsError(caught instanceof Error ? caught.message : "Document connections could not be loaded.");
      })
      .finally(() => { if (active) setConnectionsLoading(false); });
    return () => { active = false; };
  }, [connectionsRevision, selectedNodeId, tenant]);

  const visibleItems = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!tree || !needle) return tree?.items || [];
    const direct = new Set(tree.items.filter((item) => `${item.code} ${item.title} ${item.node_type}`.toLowerCase().includes(needle)).map((item) => item.id));
    const byId = new Map(tree.items.map((item) => [item.id, item]));
    for (const id of [...direct]) {
      let current = byId.get(id);
      while (current?.parent_id) {
        direct.add(current.parent_id);
        current = byId.get(current.parent_id);
      }
    }
    return tree.items.filter((item) => direct.has(item.id));
  }, [query, tree]);

  const openNode = (node: DocumentationTreeNode) => {
    const revisionId = node.document?.current_published_revision_id || (tree?.capabilities.control ? node.document?.latest_revision_id : null);
    if (node.manual_id && revisionId) navigate(`${readerBasePath}/${node.manual_id}/rev/${revisionId}/read`);
  };

  const reconcile = async () => {
    if (!tree?.capabilities.control) return;
    setBusy(true);
    setError("");
    try {
      const next = await reconcileDocumentationTree(tenant);
      setTree({ ...next, capabilities: tree.capabilities });
      setMonitor(await getReferenceMonitor(tenant));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The hierarchy could not be reconciled.");
    } finally {
      setBusy(false);
    }
  };

  const reindex = async (node: DocumentationTreeNode) => {
    const revisionId = node.document?.latest_revision_id;
    if (!revisionId) return;
    setBusy(true);
    try {
      await reindexDocumentationRevision(tenant, revisionId);
      window.setTimeout(() => void load(), 1700);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Reference indexing could not be scheduled.");
    } finally {
      setBusy(false);
    }
  };

  const renderTree = (parentId: string | null, level = 0): React.ReactNode => {
    return descendants(visibleItems, parentId).map((node) => {
      const children = descendants(visibleItems, node.id);
      const isCollapsed = collapsed.has(node.id);
      const Icon = NODE_ICONS[node.node_type];
      const status = nodeStatus(node);
      return <div key={node.id} className="dc-structure-node" style={{ "--tree-depth": level } as React.CSSProperties}>
        <div className={`dc-structure-node__row ${node.manual_id ? "is-document" : "is-group"} ${selectedNodeId === node.id ? "is-selected" : ""}`}>
          <button
            type="button"
            className="dc-structure-node__toggle"
            disabled={!children.length}
            onClick={() => setCollapsed((current) => {
              const next = new Set(current);
              if (next.has(node.id)) next.delete(node.id); else next.add(node.id);
              return next;
            })}
            aria-label={children.length ? `${isCollapsed ? "Expand" : "Collapse"} ${node.title}` : undefined}
          >
            {children.length ? isCollapsed ? <ChevronRight size={15} /> : <ChevronDown size={15} /> : <span />}
          </button>
          <button type="button" className="dc-structure-node__primary" onClick={() => setSelectedNodeId(node.id)} aria-pressed={selectedNodeId === node.id}>
            <Icon size={17} />
            <span><strong>{node.code}</strong><small>{node.title}</small></span>
          </button>
          <div className="dc-structure-node__meta">
            <DocumentControlStatus status={status.label} kind={status.kind} />
            {node.execution ? <span className="dc-structure-node__execution">{node.execution.execution_type.replaceAll("_", " ")}</span> : null}
          </div>
          <div className="dc-structure-node__actions">
            {node.manual_id && (node.document?.current_published_revision_id || (tree?.capabilities.control && node.document?.latest_revision_id)) ? <button type="button" onClick={() => openNode(node)} title="Open controlled reader"><BookOpen size={14} /></button> : null}
            {tree?.capabilities.control ? <>
            {node.manual_id ? <button type="button" onClick={() => void reindex(node)} disabled={busy || !node.document?.latest_revision_id} title="Reindex references"><RefreshCw size={14} /></button> : null}
            {executable(node) ? <button type="button" onClick={() => setExecutionNode(node)} title="Configure form execution"><Settings2 size={14} /></button> : null}
            {!String(node.metadata.system || "") ? <button type="button" onClick={() => setEditingNode(node)} title="Edit hierarchy placement"><Pencil size={14} /></button> : null}
            </> : null}
          </div>
        </div>
        {!isCollapsed && children.length ? <div className="dc-structure-node__children">{renderTree(node.id, level + 1)}</div> : null}
      </div>;
    });
  };

  const monitorIssues = monitor?.items.filter((item) => !["AUTO_RESOLVED", "VERIFIED"].includes(item.status)) || [];

  return <DocumentControlShell
    title="Document structure"
    subtitle="Governed hierarchy, version-aware cross-references, executable forms, checklists, and retained records in one controlled information graph."
    canControl={Boolean(tree?.capabilities.control)}
    actions={tree?.capabilities.control ? <button type="button" className="dc-button" onClick={() => void reconcile()} disabled={busy}><RefreshCw size={15} /> {busy ? "Working…" : "Reconcile and classify"}</button> : undefined}
  >
    <div className="dc-structure-tabs">
      <button type="button" className={tab === "STRUCTURE" ? "active" : ""} onClick={() => setTab("STRUCTURE")}><FolderTree size={15} /> Structure</button>
      {tree?.capabilities.control ? <button type="button" className={tab === "REFERENCES" ? "active" : ""} onClick={() => setTab("REFERENCES")}><Network size={15} /> Reference monitor <span>{monitorIssues.length}</span></button> : null}
    </div>

    {loading ? <DocumentControlLoading label="Building the documented-information tree…" /> : null}
    {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}

    {!loading && tree && tab === "STRUCTURE" ? <>
      <div className="dc-structure-summary">
        <div><strong>{tree.items.filter((item) => item.manual_id).length}</strong><span>controlled documents</span></div>
        <div><strong>{tree.items.filter((item) => executable(item)).length}</strong><span>forms and checklists</span></div>
        <div><strong>{tree.items.filter((item) => item.node_type === "RECORD_SERIES").length}</strong><span>record series</span></div>
        <div><strong>{Number(tree.reference_health.AUTO_RESOLVED || 0) + Number(tree.reference_health.VERIFIED || 0)}</strong><span>healthy links</span></div>
        <div className={monitorIssues.length ? "has-warning" : ""}><strong>{monitorIssues.length}</strong><span>links needing control</span></div>
      </div>
      <div className="dc-structure-toolbar">
        <label><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a manual, policy, procedure, instruction, form, checklist, or record series" /></label>
        <div><button type="button" className={mode === "TREE" ? "active" : ""} onClick={() => setMode("TREE")}><FolderTree size={14} /> Tree</button><button type="button" className={mode === "LIST" ? "active" : ""} onClick={() => setMode("LIST")}><ListTree size={14} /> Register view</button></div>
      </div>
      <div className="dc-structure-workspace">
        <div className="dc-structure-workspace__browser">
          {visibleItems.length ? mode === "TREE"
        ? <div className="dc-structure-tree">{renderTree(null)}</div>
        : <div className="dc-table-wrap"><table className="dc-table"><thead><tr><th>Code</th><th>Type and title</th><th>Hierarchy path</th><th>Revision</th><th>Execution</th><th>Action</th></tr></thead><tbody>{visibleItems.filter((node) => node.manual_id || node.node_type === "RECORD_SERIES").map((node) => {
          const status = nodeStatus(node);
          return <tr key={node.id} className={selectedNodeId === node.id ? "is-selected" : ""}><td><strong>{node.code}</strong></td><td><strong>{NODE_LABELS[node.node_type]}</strong><small>{node.title}</small></td><td><small>{node.path.split("/").filter(Boolean).map((segment) => segment.split("~")[0]).join(" › ")}</small></td><td><DocumentControlStatus status={status.label} kind={status.kind} /><small>{node.document?.latest_revision ? `Rev ${node.document.latest_revision}` : "—"}</small></td><td><strong>{node.execution?.execution_type.replaceAll("_", " ") || "Reference only"}</strong><small>{node.execution?.record_series_node_id ? `${node.execution.retention_years || "—"} year retention` : "No generated records"}</small></td><td><button type="button" className="dc-button" onClick={() => setSelectedNodeId(node.id)}><Network size={14} /> Inspect</button>{node.manual_id ? <button type="button" className="dc-button" disabled={!node.document?.current_published_revision_id && !tree?.capabilities.control} onClick={() => openNode(node)}><BookOpen size={14} /> Open</button> : null}</td></tr>;
        })}</tbody></table></div>
        : <DocumentControlEmpty icon={Search} title="No hierarchy item matches the search" message="Clear the search or use a document code, title, type, or record-series name." />}
        </div>
        <NodeConnectionsInspector
          connections={connections}
          loading={connectionsLoading}
          error={connectionsError}
          onRetry={() => setConnectionsRevision((current) => current + 1)}
          onSelect={setSelectedNodeId}
          onOpen={openNode}
        />
      </div>
    </> : null}

    {!loading && tree && tab === "REFERENCES" ? <ReferenceMonitor
      response={monitor}
      onRefresh={() => void load()}
      onResolve={setResolvingReference}
      onOpenSource={(item) => navigate(`${readerBasePath}/${item.source_manual.id}/rev/${item.source_revision_id}/read${item.source_page_number ? `?page=${item.source_page_number}` : ""}`)}
    /> : null}

    {editingNode && tree ? <NodeEditor node={editingNode} tree={tree} tenant={tenant} onClose={() => setEditingNode(null)} onSaved={(next) => { setTree(next); setConnectionsRevision((current) => current + 1); setEditingNode(null); }} /> : null}
    {executionNode && tree ? <ExecutionEditor node={executionNode} tree={tree} tenant={tenant} onClose={() => setExecutionNode(null)} onSaved={() => { setExecutionNode(null); void load(); }} /> : null}
    {resolvingReference && tree ? <ReferenceResolver reference={resolvingReference} tree={tree} tenant={tenant} onClose={() => setResolvingReference(null)} onSaved={() => { setResolvingReference(null); void load(); }} /> : null}
  </DocumentControlShell>;
}

function connectionStatusKind(status: string): "success" | "warning" | "danger" | "neutral" | "info" {
  if (["CONFIRMED", "VERIFIED", "AUTO_RESOLVED", "ACCEPTED"].includes(status)) return "success";
  if (["BROKEN", "REJECTED", "MISSING", "MISMATCH", "RETURNED"].includes(status)) return "danger";
  if (["UNRESOLVED", "AMBIGUOUS", "DETECTED", "PENDING_REVIEW", "SUBMITTED"].includes(status)) return "warning";
  return "neutral";
}

function connectionDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" }).format(parsed);
}

function NodeConnectionsInspector({ connections, loading, error, onRetry, onSelect, onOpen }: {
  connections: DocumentationNodeConnections | null;
  loading: boolean;
  error: string;
  onRetry: () => void;
  onSelect: (nodeId: string) => void;
  onOpen: (node: DocumentationTreeNode) => void;
}) {
  if (loading && !connections) return <aside className="dc-node-inspector"><DocumentControlLoading label="Tracing document lineage…" /></aside>;
  if (error && !connections) return <aside className="dc-node-inspector"><DocumentControlError message={error} retry={onRetry} /></aside>;
  if (!connections) return <aside className="dc-node-inspector"><DocumentControlEmpty icon={Network} title="Select a hierarchy item" message="Choose any manual, related document, form, checklist, or record series to see its full controlled lineage." /></aside>;

  const { node } = connections;
  const relationships = [...connections.governed_relationships, ...connections.detected_references];
  const uniqueWorkflowNodes = connections.workflow_nodes;
  const canOpen = (item: DocumentationTreeNode) => Boolean(item.manual_id && (item.document?.current_published_revision_id || (connections.capabilities.control && item.document?.latest_revision_id)));

  return <aside className="dc-node-inspector" aria-live="polite">
    <header className="dc-node-inspector__header">
      <div><span>{NODE_LABELS[node.node_type]}</span><h2>{node.code}</h2><p>{node.title}</p></div>
      {canOpen(node) ? <button type="button" className="dc-button dc-button--primary" onClick={() => onOpen(node)}><BookOpen size={14} /> Open reader</button> : null}
    </header>

    <nav className="dc-node-inspector__breadcrumbs" aria-label="Document hierarchy path">
      {connections.breadcrumbs.map((item, index) => <span key={item.id}><button type="button" onClick={() => onSelect(item.id)}>{item.code}</button>{index < connections.breadcrumbs.length - 1 ? <ChevronRight size={12} /> : null}</span>)}
    </nav>

    <div className="dc-node-inspector__flow" aria-label="Controlled information lineage">
      <span><BookOpen size={15} /> Manual or procedure</span><ArrowRight size={14} />
      <span><Link2 size={15} /> Related documents</span><ArrowRight size={14} />
      <span><ClipboardCheck size={15} /> Forms &amp; checklists</span><ArrowRight size={14} />
      <span><History size={15} /> Associated records</span>
    </div>

    <section className="dc-node-inspector__section">
      <div className="dc-node-inspector__section-title"><div><h3>Contained documents and templates</h3><p>Directly subordinate items in the controlled hierarchy.</p></div><strong>{connections.children.length}</strong></div>
      {connections.children.length ? <div className="dc-node-inspector__links">{connections.children.map((item) => <article key={item.id}>
        <button type="button" className="dc-node-inspector__link-main" onClick={() => onSelect(item.id)}><span>{item.code}</span><strong>{item.title}</strong><small>{NODE_LABELS[item.node_type]}</small></button>
        {canOpen(item) ? <button type="button" className="dc-node-inspector__open" onClick={() => onOpen(item)} aria-label={`Open ${item.code} in reader`}><BookOpen size={14} /></button> : null}
      </article>)}</div> : <p className="dc-node-inspector__empty">No direct child documents are registered under this item.</p>}
    </section>

    <section className="dc-node-inspector__section">
      <div className="dc-node-inspector__section-title"><div><h3>Related documentation</h3><p>Confirmed relationships and detected cross-references in both directions.</p></div><strong>{relationships.length}</strong></div>
      {relationships.length ? <div className="dc-node-inspector__relationships">{relationships.slice(0, 30).map((edge) => <article key={`${edge.kind}-${edge.id}-${edge.direction}`}>
        <div className="dc-node-inspector__relationship-copy"><span>{edge.direction === "OUTGOING" ? "Uses / points to" : "Referenced by"}</span><button type="button" onClick={() => onSelect(edge.related_node.id)}>{edge.related_node.code} · {edge.related_node.title}</button><small>{edge.relationship_type.replaceAll("_", " ")}{edge.source_page_number || edge.page_number ? ` · page ${edge.source_page_number || edge.page_number}` : ""}</small></div>
        <DocumentControlStatus status={edge.status} kind={connectionStatusKind(edge.status)} />
        {canOpen(edge.related_node) ? <button type="button" className="dc-node-inspector__open" onClick={() => onOpen(edge.related_node)} aria-label={`Open related document ${edge.related_node.code}`}><BookOpen size={14} /></button> : null}
      </article>)}</div> : <p className="dc-node-inspector__empty">No visible governed or detected document relationships are connected to this item.</p>}
      {relationships.length > 30 ? <p className="dc-node-inspector__more">Showing 30 of {relationships.length} visible relationship occurrences.</p> : null}
    </section>

    <section className="dc-node-inspector__section">
      <div className="dc-node-inspector__section-title"><div><h3>Work records, forms &amp; checklists</h3><p>Executable templates and the record series they feed.</p></div><strong>{uniqueWorkflowNodes.length}</strong></div>
      {uniqueWorkflowNodes.length ? <div className="dc-node-inspector__links">{uniqueWorkflowNodes.map((item) => <article key={item.id}>
        <button type="button" className="dc-node-inspector__link-main" onClick={() => onSelect(item.id)}><span>{item.code}</span><strong>{item.title}</strong><small>{NODE_LABELS[item.node_type]}{item.execution?.retention_years ? ` · ${item.execution.retention_years} year retention` : ""}</small></button>
        {canOpen(item) ? <button type="button" className="dc-node-inspector__open" onClick={() => onOpen(item)} aria-label={`Open ${item.code} in reader`}><BookOpen size={14} /></button> : null}
      </article>)}</div> : <p className="dc-node-inspector__empty">No executable form, checklist, register, or output record series is linked here yet.</p>}
    </section>

    <section className="dc-node-inspector__section">
      <div className="dc-node-inspector__section-title"><div><h3>Associated retained records</h3><p>{connections.records.scope === "ALL" ? "All tenant records visible to Document Control." : "Only records submitted by you are shown."}</p></div><strong>{connections.records.total}</strong></div>
      {connections.records.items.length ? <div className="dc-node-inspector__records">{connections.records.items.map((record) => <article key={record.id}>
        <div><strong>{record.record_number}</strong><span>{record.template?.code || node.code} · {connectionDate(record.submitted_at)}</span><small>{record.artifact_filename}{record.retention_years ? ` · retain ${record.retention_years} years` : ""}</small></div>
        <DocumentControlStatus status={record.status} kind={connectionStatusKind(record.status)} />
        <a className="dc-node-inspector__open" href={record.download_url} target="_blank" rel="noreferrer" aria-label={`Open retained record ${record.record_number}`}><BookOpen size={14} /></a>
      </article>)}</div> : <p className="dc-node-inspector__empty">No associated retained records are visible for this item yet.</p>}
      {connections.records.total > connections.records.limit ? <p className="dc-node-inspector__more">Showing the latest {connections.records.limit} of {connections.records.total} records.</p> : null}
    </section>
    {loading ? <div className="dc-node-inspector__refreshing"><RefreshCw size={13} /> Refreshing lineage…</div> : null}
    {error ? <div className="dc-node-inspector__refreshing is-error"><AlertTriangle size={13} /> {error} <button type="button" onClick={onRetry}>Retry</button></div> : null}
  </aside>;
}

function ReferenceMonitor({ response, onRefresh, onResolve, onOpenSource }: {
  response: ReferenceMonitorResponse | null;
  onRefresh: () => void;
  onResolve: (item: ReferenceMonitorResponse["items"][number]) => void;
  onOpenSource: (item: ReferenceMonitorResponse["items"][number]) => void;
}) {
  const [status, setStatus] = useState("ISSUES");
  const items = (response?.items || []).filter((item) => status === "ALL" || (status === "HEALTHY" ? ["AUTO_RESOLVED", "VERIFIED"].includes(item.status) : !["AUTO_RESOLVED", "VERIFIED"].includes(item.status)));
  return <section className="dc-reference-monitor">
    <header><div><h2>Cross-reference integrity</h2><p>Every detected citation is checked against the current tenant register. Broken, ambiguous, outdated, and unresolved occurrences remain visible until controlled.</p></div><button type="button" className="dc-button" onClick={onRefresh}><RefreshCw size={14} /> Refresh</button></header>
    <div className="dc-reference-monitor__filters"><button type="button" className={status === "ISSUES" ? "active" : ""} onClick={() => setStatus("ISSUES")}>Needs control</button><button type="button" className={status === "HEALTHY" ? "active" : ""} onClick={() => setStatus("HEALTHY")}>Healthy</button><button type="button" className={status === "ALL" ? "active" : ""} onClick={() => setStatus("ALL")}>All</button></div>
    {items.length ? <div className="dc-table-wrap"><table className="dc-table"><thead><tr><th>Reference</th><th>Source occurrence</th><th>Resolution</th><th>Confidence</th><th>Action</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}>
      <td><strong>{item.raw_token}</strong><small>{item.relationship_type.replaceAll("_", " ")}</small></td>
      <td><strong>{item.source_manual.code}</strong><small>{item.source_manual.title}{item.source_page_number ? ` · page ${item.source_page_number}` : ""}</small><p>{item.source_context}</p></td>
      <td><DocumentControlStatus status={item.status} kind={["AUTO_RESOLVED", "VERIFIED"].includes(item.status) ? "success" : item.status === "BROKEN" ? "danger" : "warning"} /><small>{item.target_manual?.code ? `${item.target_manual.code} · ${item.target_manual.title}` : item.candidates.length ? `${item.candidates.length} candidate targets` : "No registered target"}</small></td>
      <td><strong>{item.confidence_percent}%</strong></td>
      <td><button type="button" className="dc-button" onClick={() => onOpenSource(item)}><BookOpen size={14} /> Source</button>{!["AUTO_RESOLVED", "VERIFIED"].includes(item.status) || item.candidates.length ? <button type="button" className="dc-button dc-button--primary" onClick={() => onResolve(item)}>Resolve</button> : null}</td>
    </tr>)}</tbody></table></div> : <DocumentControlEmpty icon={CheckCircle2} title="No references in this view" message={status === "ISSUES" ? "The current reference graph has no broken, ambiguous, outdated, or unresolved occurrences." : "No references match this filter."} />}
  </section>;
}

function Dialog({ title, description, children, onClose }: { title: string; description: string; children: React.ReactNode; onClose: () => void }) {
  return <div className="publications-upload-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="publications-upload-dialog dc-structure-dialog" role="dialog" aria-modal="true" aria-label={title}><header><div><h2>{title}</h2><p>{description}</p></div><button type="button" onClick={onClose}><X size={18} /></button></header>{children}</section></div>;
}

function NodeEditor({ node, tree, tenant, onClose, onSaved }: { node: DocumentationTreeNode; tree: DocumentationTree; tenant: string; onClose: () => void; onSaved: (tree: DocumentationTree) => void }) {
  const [parentId, setParentId] = useState(node.parent_id || "");
  const [nodeType, setNodeType] = useState(node.node_type);
  const [code, setCode] = useState(node.code);
  const [title, setTitle] = useState(node.title);
  const [aliases, setAliases] = useState(Array.isArray(node.metadata.aliases) ? (node.metadata.aliases as string[]).filter((value) => value !== node.code).join("\n") : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      onSaved(await updateDocumentationNode(tenant, node.id, { parent_id: parentId || null, node_type: nodeType, code, title, order_index: node.order_index, aliases: aliases.split(/[\n,;]+/).map((value) => value.trim()).filter(Boolean) }));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The hierarchy node could not be updated."); }
    finally { setBusy(false); }
  };
  return <Dialog title={`Edit ${node.code}`} description="Hierarchy changes affect discovery and reference context only. They never alter approved document content." onClose={onClose}><form className="dc-form" onSubmit={submit}>
    <label><span>Document type</span><select value={nodeType} onChange={(event) => setNodeType(event.target.value as DocumentationNodeType)}>{Object.entries(NODE_LABELS).filter(([type]) => type !== "ROOT").map(([type, label]) => <option key={type} value={type}>{label}</option>)}</select></label>
    <label><span>Parent</span><select value={parentId} onChange={(event) => setParentId(event.target.value)}><option value="">No parent</option>{tree.items.filter((item) => item.id !== node.id && !item.path.startsWith(`${node.path}/`)).map((item) => <option key={item.id} value={item.id}>{"—".repeat(Math.min(item.depth, 6))} {item.code} · {item.title}</option>)}</select></label>
    <label><span>Controlled code</span><input value={code} onChange={(event) => setCode(event.target.value)} required /></label>
    <label className="wide"><span>Title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
    <label className="wide"><span>Aliases detected in documents</span><textarea value={aliases} onChange={(event) => setAliases(event.target.value)} placeholder="QAM 51&#10;QAM-051&#10;Quality Form 51" /></label>
    {error ? <div className="dc-form__error">{error}</div> : null}<div className="dc-form__actions"><button type="button" className="dc-button" onClick={onClose}>Cancel</button><button type="submit" className="dc-button dc-button--primary" disabled={busy}>{busy ? "Saving…" : "Save hierarchy"}</button></div>
  </form></Dialog>;
}

function ExecutionEditor({ node, tree, tenant, onClose, onSaved }: { node: DocumentationTreeNode; tree: DocumentationTree; tenant: string; onClose: () => void; onSaved: () => void }) {
  const current = node.execution;
  const [executionType, setExecutionType] = useState<DocumentationExecutionProfile["execution_type"]>(current?.execution_type || (node.document?.source_type === "PDF" ? "PDF_ACROFORM" : node.node_type === "CHECKLIST" ? "CHECKLIST" : "DOWNLOADABLE_TEMPLATE"));
  const [submissionMode, setSubmissionMode] = useState<DocumentationExecutionProfile["submission_mode"]>(current?.submission_mode || "FILL_AND_SUBMIT");
  const [seriesId, setSeriesId] = useState(current?.record_series_node_id || "");
  const [retention, setRetention] = useState(String(current?.retention_years || 7));
  const [allowDownload, setAllowDownload] = useState(current?.allow_download ?? true);
  const [allowDraft, setAllowDraft] = useState(current?.allow_save_draft ?? true);
  const [requiresSignature, setRequiresSignature] = useState(current?.requires_signature ?? false);
  const [requiresReview, setRequiresReview] = useState(current?.requires_review ?? false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!node.manual_id) return; setBusy(true); setError("");
    try {
      await updateDocumentationExecutionProfile(tenant, node.manual_id, {
        execution_type: executionType, submission_mode: submissionMode, record_series_node_id: seriesId || null, retention_years: Number(retention) || null, naming_pattern: current?.naming_pattern || "{code}-{date}-{sequence}", allow_download: allowDownload, allow_save_draft: allowDraft, requires_signature: requiresSignature, requires_review: requiresReview, schema: current?.schema || {}, access_scope: current?.access_scope || {}, metadata: current?.metadata || {}, version: current?.version || 1, expected_version: current?.version || null,
      }); onSaved();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Form execution controls could not be saved."); }
    finally { setBusy(false); }
  };
  return <Dialog title={`Configure ${node.code}`} description="Define whether this controlled template can be filled, submitted, reviewed, and retained as a record." onClose={onClose}><form className="dc-form" onSubmit={submit}>
    <label><span>Execution type</span><select value={executionType} onChange={(event) => setExecutionType(event.target.value as DocumentationExecutionProfile["execution_type"])}><option value="PDF_ACROFORM">Interactive PDF AcroForm</option><option value="CHECKLIST">Portal checklist</option><option value="PORTAL_FORM">Portal form</option><option value="DOWNLOADABLE_TEMPLATE">Downloadable template</option><option value="HYBRID">Hybrid form</option><option value="NONE">Reference only</option></select></label>
    <label><span>Submission mode</span><select value={submissionMode} onChange={(event) => setSubmissionMode(event.target.value as DocumentationExecutionProfile["submission_mode"])}><option value="FILL_AND_SUBMIT">Fill PDF and submit</option><option value="DOWNLOAD_AND_UPLOAD">Download and upload completed copy</option><option value="PORTAL_SUBMISSION">Portal submission</option><option value="DOWNLOAD_ONLY">Download only</option></select></label>
    <label className="wide"><span>Output record series</span><select value={seriesId} onChange={(event) => setSeriesId(event.target.value)} required={submissionMode !== "DOWNLOAD_ONLY"}><option value="">No generated record</option>{tree.items.filter((item) => item.node_type === "RECORD_SERIES").map((item) => <option key={item.id} value={item.id}>{item.code} · {item.title}</option>)}</select></label>
    <label><span>Retention period (years)</span><input type="number" min={1} max={100} value={retention} onChange={(event) => setRetention(event.target.value)} /></label>
    <label><span><input type="checkbox" checked={allowDownload} onChange={(event) => setAllowDownload(event.target.checked)} /> Permit controlled download</span></label>
    <label><span><input type="checkbox" checked={allowDraft} onChange={(event) => setAllowDraft(event.target.checked)} /> Allow local working draft</span></label>
    <label><span><input type="checkbox" checked={requiresSignature} onChange={(event) => setRequiresSignature(event.target.checked)} /> Signature required</span></label>
    <label><span><input type="checkbox" checked={requiresReview} onChange={(event) => setRequiresReview(event.target.checked)} /> Quality review after submission</span></label>
    {error ? <div className="dc-form__error">{error}</div> : null}<div className="dc-form__actions"><button type="button" className="dc-button" onClick={onClose}>Cancel</button><button type="submit" className="dc-button dc-button--primary" disabled={busy}>{busy ? "Saving…" : "Save execution controls"}</button></div>
  </form></Dialog>;
}

function ReferenceResolver({ reference, tree, tenant, onClose, onSaved }: { reference: ReferenceMonitorResponse["items"][number]; tree: DocumentationTree; tenant: string; onClose: () => void; onSaved: () => void }) {
  const options = tree.items.filter((item) => item.manual_id && item.document?.current_published_revision_id);
  const [targetId, setTargetId] = useState(reference.target_manual?.id || reference.candidates[0]?.manual_id || "");
  const [relationship, setRelationship] = useState(reference.relationship_type || "REFERENCES");
  const [comments, setComments] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try { await resolveDocumentationReference(tenant, reference.id, { target_manual_id: targetId, relationship_type: relationship, resolution_policy: "CURRENT_EFFECTIVE", comments }); onSaved(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "The reference could not be resolved."); }
    finally { setBusy(false); }
  };
  return <Dialog title={`Resolve ${reference.raw_token}`} description="Select the effective controlled target. The decision is retained and rechecked whenever either document changes." onClose={onClose}><form className="dc-form" onSubmit={submit}>
    <div className="dc-callout"><AlertTriangle size={17} /><div><strong>{reference.source_manual.code}{reference.source_page_number ? ` · page ${reference.source_page_number}` : ""}</strong><div>{reference.source_context}</div></div></div>
    <label className="wide"><span>Controlled target</span><select value={targetId} onChange={(event) => setTargetId(event.target.value)} required><option value="">Select effective document</option>{options.map((item) => <option key={item.manual_id} value={item.manual_id || ""}>{item.code} · {item.title} · {NODE_LABELS[item.node_type]}</option>)}</select></label>
    <label><span>Relationship</span><select value={relationship} onChange={(event) => setRelationship(event.target.value)}><option value="REFERENCES">References</option><option value="IMPLEMENTS">Implements</option><option value="USES_FORM">Uses form</option><option value="USES_CHECKLIST">Uses checklist</option><option value="UPDATES_REGISTER">Updates register</option><option value="CREATES_RECORD">Creates record</option></select></label>
    <label className="wide"><span>Verification basis</span><textarea value={comments} onChange={(event) => setComments(event.target.value)} required placeholder="Explain how the intended target was confirmed." /></label>
    {error ? <div className="dc-form__error">{error}</div> : null}<div className="dc-form__actions"><button type="button" className="dc-button" onClick={onClose}>Cancel</button><button type="submit" className="dc-button dc-button--primary" disabled={busy || !targetId || comments.trim().length < 3}>{busy ? "Resolving…" : "Verify reference"}</button></div>
  </form></Dialog>;
}
