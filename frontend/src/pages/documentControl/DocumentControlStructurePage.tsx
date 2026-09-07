import { useEffect, useMemo, useState, type CSSProperties } from "react";
import {
  AlertTriangle,
  BookOpen,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  ExternalLink,
  FileCheck2,
  FileText,
  FolderTree,
  GitBranch,
  Link2,
  Network,
  RefreshCw,
  Search,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  getDocumentationNodeConnections,
  getDocumentationTree,
  getReferenceMonitor,
  reconcileDocumentationTree,
  type DocumentationConnection,
  type DocumentationNodeConnections,
  type DocumentationTree,
  type DocumentationTreeNode,
} from "../../services/documentation";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
  useDocumentControlRoute,
} from "./DocumentControlShell";
import "./documentControlStructure.css";

type StructureView = "hierarchy" | "references";

const EXECUTABLE_TYPES = new Set(["FORM", "CHECKLIST", "REGISTER"]);

function statusKind(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  const value = status.toUpperCase();
  if (["ACTIVE", "PUBLISHED", "VERIFIED", "ACCEPTED", "SUBMITTED"].includes(value)) return "success";
  if (["BROKEN", "MISSING", "MISMATCH", "RETURNED", "REJECTED"].includes(value)) return "danger";
  if (["UNRESOLVED", "OUTDATED", "PENDING_REVIEW", "AUTO_RESOLVED"].includes(value)) return "warning";
  return "neutral";
}

function nodeIcon(type: DocumentationTreeNode["node_type"]) {
  if (type === "ROOT" || type === "MANAGEMENT_SYSTEM") return FolderTree;
  if (EXECUTABLE_TYPES.has(type)) return ClipboardCheck;
  if (type === "RECORD" || type === "RECORD_SERIES") return FileCheck2;
  return FileText;
}

function nodeLabel(node: DocumentationTreeNode): string {
  return node.node_type.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (value) => value.toUpperCase());
}

function hierarchyRows(
  items: DocumentationTreeNode[],
  expanded: Set<string>,
  search: string,
): DocumentationTreeNode[] {
  const byParent = new Map<string, DocumentationTreeNode[]>();
  const ids = new Set(items.map((item) => item.id));
  for (const item of items) {
    const parent = item.parent_id && ids.has(item.parent_id) ? item.parent_id : "";
    byParent.set(parent, [...(byParent.get(parent) || []), item]);
  }
  for (const rows of byParent.values()) rows.sort((a, b) => a.order_index - b.order_index || a.title.localeCompare(b.title));

  const needle = search.trim().toLowerCase();
  const included = new Set<string>();
  if (needle) {
    const byId = new Map(items.map((item) => [item.id, item]));
    for (const item of items) {
      const searchable = `${item.code} ${item.title} ${item.node_type} ${item.path}`.toLowerCase();
      if (!searchable.includes(needle)) continue;
      let cursor: DocumentationTreeNode | undefined = item;
      while (cursor && !included.has(cursor.id)) {
        included.add(cursor.id);
        cursor = cursor.parent_id ? byId.get(cursor.parent_id) : undefined;
      }
    }
  }

  const rows: DocumentationTreeNode[] = [];
  const append = (parentId: string) => {
    for (const item of byParent.get(parentId) || []) {
      if (needle && !included.has(item.id)) continue;
      rows.push(item);
      if (needle || expanded.has(item.id)) append(item.id);
    }
  };
  append("");
  return rows;
}

function ConnectionCard({ edge, onSelect }: { edge: DocumentationConnection; onSelect: (id: string) => void }) {
  const label = edge.kind === "DETECTED_REFERENCE" ? "Detected reference" : "Governed relationship";
  return <article>
    <Link2 size={15} aria-hidden />
    <div className="dc-node-inspector__relationship-copy">
      <span>{label} · {edge.direction.toLowerCase()}</span>
      <button type="button" onClick={() => onSelect(edge.related_node.id)}>{edge.related_node.code} · {edge.related_node.title}</button>
      <small>{edge.relationship_type.replaceAll("_", " ")} · {edge.exact_quote || edge.source_quote || edge.exact_token || edge.raw_token || "No extracted quotation"}</small>
    </div>
    <DocumentControlStatus status={edge.status} kind={statusKind(edge.status)} />
  </article>;
}

function NodeInspector({
  loading,
  error,
  detail,
  basePath,
  onSelect,
  onRetry,
}: {
  loading: boolean;
  error: string;
  detail: DocumentationNodeConnections | null;
  basePath: string;
  onSelect: (id: string) => void;
  onRetry: () => void;
}) {
  const navigate = useNavigate();
  if (loading && !detail) return <aside className="dc-node-inspector"><DocumentControlLoading label="Loading lineage…" /></aside>;
  if (error && !detail) return <aside className="dc-node-inspector"><DocumentControlError message={error} retry={onRetry} /></aside>;
  if (!detail) return <aside className="dc-node-inspector"><DocumentControlEmpty icon={GitBranch} title="Select a structure node" message="Selection reveals its lineage and records here. It never opens the reader automatically." /></aside>;

  const relationships = [...detail.governed_relationships, ...detail.detected_references];
  return <aside className="dc-node-inspector" aria-label="Selected document lineage">
    <header className="dc-node-inspector__header">
      <div><span>{nodeLabel(detail.node)}</span><h2>{detail.node.code}</h2><p>{detail.node.title}</p></div>
      {detail.node.manual_id ? <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library/${detail.node.manual_id}`)}><BookOpen size={14} /> Open document</button> : null}
    </header>
    <nav className="dc-node-inspector__breadcrumbs" aria-label="Hierarchy path">
      {detail.breadcrumbs.map((item, index) => <span key={item.id}><button type="button" onClick={() => onSelect(item.id)}>{item.code}</button>{index < detail.breadcrumbs.length - 1 ? <ChevronRight size={12} /> : null}</span>)}
    </nav>
    <div className="dc-node-inspector__flow" aria-label="Controlled information lineage">
      <span><BookOpen size={15} /> Manual / policy</span><ChevronRight size={13} />
      <span><GitBranch size={15} /> Procedure / instruction</span><ChevronRight size={13} />
      <span><ClipboardCheck size={15} /> Form / checklist</span><ChevronRight size={13} />
      <span><FileCheck2 size={15} /> Completed record</span>
    </div>

    <section className="dc-node-inspector__section">
      <div className="dc-node-inspector__section-title"><div><h3>Direct children</h3><p>Controlled items immediately below this node.</p></div><strong>{detail.children.length}</strong></div>
      <div className="dc-node-inspector__links">
        {detail.children.map((item) => { const Icon = nodeIcon(item.node_type); return <article key={item.id}><Icon size={15} /><button type="button" className="dc-node-inspector__link-main" onClick={() => onSelect(item.id)}><span>{nodeLabel(item)}</span><strong>{item.code} · {item.title}</strong></button><ChevronRight size={14} /></article>; })}
        {!detail.children.length ? <p className="dc-node-inspector__empty">No direct child is recorded.</p> : null}
      </div>
    </section>

    <section className="dc-node-inspector__section">
      <div className="dc-node-inspector__section-title"><div><h3>Executable and output chain</h3><p>Forms, checklists, registers and record series reachable below this selection or a directly related document.</p></div><strong>{detail.workflow_nodes.length}</strong></div>
      <div className="dc-node-inspector__links">
        {detail.workflow_nodes.map((item) => { const Icon = nodeIcon(item.node_type); return <article key={item.id}><Icon size={15} /><button type="button" className="dc-node-inspector__link-main" onClick={() => onSelect(item.id)}><span>{nodeLabel(item)}</span><strong>{item.code} · {item.title}</strong><small>{item.execution ? item.execution.submission_mode.replaceAll("_", " ") : "Controlled output series"}</small></button><ChevronRight size={14} /></article>; })}
        {!detail.workflow_nodes.length ? <p className="dc-node-inspector__empty">No executable form, checklist, register or output series is connected to this branch.</p> : null}
      </div>
    </section>

    <section className="dc-node-inspector__section">
      <div className="dc-node-inspector__section-title"><div><h3>Governed and detected links</h3><p>Confirmed relationships stay distinct from machine-detected references.</p></div><strong>{relationships.length}</strong></div>
      <div className="dc-node-inspector__relationships">
        {relationships.map((edge) => <ConnectionCard key={`${edge.kind}:${edge.id}:${edge.direction}`} edge={edge} onSelect={onSelect} />)}
        {!relationships.length ? <p className="dc-node-inspector__empty">No cross-document relationship is visible for this node.</p> : null}
      </div>
    </section>

    <section className="dc-node-inspector__section">
      <div className="dc-node-inspector__section-title"><div><h3>Completed records</h3><p>{detail.records.scope === "ALL" ? "All visible records for this lineage." : "Only records submitted by you are shown."} Latest {detail.records.limit} retained.</p></div><strong>{detail.records.total}</strong></div>
      <div className="dc-node-inspector__records">
        {detail.records.items.map((record) => <article key={record.id}><FileCheck2 size={15} /><div><strong>{record.record_number}</strong><span>{record.template ? `${record.template.code} · ${record.template.title}` : record.artifact_filename}</span><small>{record.submitted_at ? new Date(record.submitted_at).toLocaleString() : "Submission time not recorded"} · {record.retention_years ? `${record.retention_years} year retention` : "Retention not set"}</small></div><DocumentControlStatus status={record.status} kind={statusKind(record.status)} /><button type="button" className="dc-node-inspector__open" aria-label={`Open record ${record.record_number}`} onClick={() => navigate(`${basePath}/structure/records/${record.id}`)}><ExternalLink size={14} /></button></article>)}
        {!detail.records.items.length ? <p className="dc-node-inspector__empty">No completed record is available in your permitted scope.</p> : null}
        {detail.records.total > detail.records.items.length ? <p className="dc-node-inspector__more">Showing {detail.records.items.length} of {detail.records.total} records. Use Reports for the full retention register.</p> : null}
      </div>
    </section>
    {loading || error ? <div className={`dc-node-inspector__refreshing${error ? " is-error" : ""}`}>{loading ? "Refreshing lineage…" : error}<button type="button" onClick={onRetry}>Retry</button></div> : null}
  </aside>;
}

export default function DocumentControlStructurePage() {
  const { tenant, basePath } = useDocumentControlRoute();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [tree, setTree] = useState<DocumentationTree | null>(null);
  const [treeError, setTreeError] = useState("");
  const [treeLoading, setTreeLoading] = useState(true);
  const [detail, setDetail] = useState<DocumentationNodeConnections | null>(null);
  const [detailError, setDetailError] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [view, setView] = useState<StructureView>(params.get("view") === "references" ? "references" : "hierarchy");
  const [referenceStatus, setReferenceStatus] = useState("");
  const [referenceData, setReferenceData] = useState<Awaited<ReturnType<typeof getReferenceMonitor>> | null>(null);
  const [referenceError, setReferenceError] = useState("");
  const [referenceLoading, setReferenceLoading] = useState(false);
  const [reconciling, setReconciling] = useState(false);

  const selectedId = params.get("node") || "";

  const loadTree = async (reconcile = false) => {
    if (!tenant) return;
    setTreeLoading(true);
    setTreeError("");
    try {
      const next = reconcile ? await reconcileDocumentationTree(tenant) : await getDocumentationTree(tenant);
      setTree(next);
      setExpanded((current) => {
        if (current.size) return current;
        return new Set(next.items.filter((item) => item.depth < 2).map((item) => item.id));
      });
      const nextSelected = selectedId && next.items.some((item) => item.id === selectedId)
        ? selectedId
        : next.root_id || next.items[0]?.id || "";
      if (nextSelected && nextSelected !== selectedId) {
        const nextParams = new URLSearchParams(params);
        nextParams.set("node", nextSelected);
        setParams(nextParams, { replace: true });
      }
    } catch (caught) {
      setTreeError(caught instanceof Error ? caught.message : "The document hierarchy could not be loaded.");
    } finally {
      setTreeLoading(false);
    }
  };

  useEffect(() => { void loadTree(); }, [tenant]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!tenant || !selectedId) { setDetail(null); return; }
    let active = true;
    setDetailLoading(true);
    setDetailError("");
    getDocumentationNodeConnections(tenant, selectedId)
      .then((value) => { if (active) setDetail(value); })
      .catch((caught) => { if (active) setDetailError(caught instanceof Error ? caught.message : "The selected lineage could not be loaded."); })
      .finally(() => { if (active) setDetailLoading(false); });
    return () => { active = false; };
  }, [selectedId, tenant]);

  const loadReferences = async () => {
    if (!tenant || !tree?.capabilities.control) return;
    setReferenceLoading(true);
    setReferenceError("");
    try { setReferenceData(await getReferenceMonitor(tenant, referenceStatus || undefined)); }
    catch (caught) { setReferenceError(caught instanceof Error ? caught.message : "Reference monitoring could not be loaded."); }
    finally { setReferenceLoading(false); }
  };
  useEffect(() => { if (view === "references") void loadReferences(); }, [view, referenceStatus, tenant, tree?.capabilities.control]); // eslint-disable-line react-hooks/exhaustive-deps

  const rows = useMemo(() => hierarchyRows(tree?.items || [], expanded, search), [expanded, search, tree?.items]);
  const nodeIds = useMemo(() => new Set((tree?.items || []).map((item) => item.id)), [tree?.items]);
  const childCounts = useMemo(() => {
    const values = new Map<string, number>();
    for (const item of tree?.items || []) if (item.parent_id && nodeIds.has(item.parent_id)) values.set(item.parent_id, (values.get(item.parent_id) || 0) + 1);
    return values;
  }, [nodeIds, tree?.items]);
  const selectNode = (nodeId: string) => {
    const next = new URLSearchParams(params);
    next.set("node", nodeId);
    next.delete("view");
    setView("hierarchy");
    setParams(next, { replace: true });
  };
  const setActiveView = (nextView: StructureView) => {
    setView(nextView);
    const next = new URLSearchParams(params);
    if (nextView === "references") next.set("view", "references"); else next.delete("view");
    setParams(next, { replace: true });
  };
  const runReconcile = async () => {
    setReconciling(true);
    try { await loadTree(true); }
    finally { setReconciling(false); }
  };

  const documentCount = (tree?.items || []).filter((item) => item.manual_id).length;
  const executableCount = (tree?.items || []).filter((item) => EXECUTABLE_TYPES.has(item.node_type)).length;
  const unresolvedCount = Object.entries(tree?.reference_health || {}).filter(([key]) => !["VERIFIED", "RESOLVED"].includes(key)).reduce((total, [, count]) => total + count, 0);

  return <DocumentControlShell
    title="Document structure"
    subtitle="Trace controlled information from governing manuals through procedures and executable forms to retained records."
    canControl={tree?.capabilities.control ?? false}
    actions={tree?.capabilities.control ? <button type="button" className="dc-button" disabled={reconciling} onClick={() => void runReconcile()}><RefreshCw size={14} className={reconciling ? "is-spinning" : ""} /> {reconciling ? "Reconciling…" : "Reconcile sources"}</button> : undefined}
  >
    <div className="dc-structure-tabs" role="tablist" aria-label="Document structure view">
      <button type="button" role="tab" aria-selected={view === "hierarchy"} className={view === "hierarchy" ? "active" : ""} onClick={() => setActiveView("hierarchy")}><FolderTree size={15} /> Hierarchy <span>{tree?.items.length || 0}</span></button>
      {tree?.capabilities.control ? <button type="button" role="tab" aria-selected={view === "references"} className={view === "references" ? "active" : ""} onClick={() => setActiveView("references")}><Network size={15} /> Reference review <span>{unresolvedCount}</span></button> : null}
    </div>

    {treeError ? <DocumentControlError message={treeError} retry={() => void loadTree()} /> : null}
    {treeLoading && !tree ? <DocumentControlLoading label="Loading controlled-information structure…" /> : null}
    {tree ? <div className="dc-structure-summary">
      <div><strong>{tree.items.length}</strong><span>Visible structure nodes</span></div>
      <div><strong>{documentCount}</strong><span>Controlled documents</span></div>
      <div><strong>{executableCount}</strong><span>Forms, checklists & registers</span></div>
      <div className={unresolvedCount ? "has-warning" : ""}><strong>{tree.capabilities.control ? unresolvedCount : "—"}</strong><span>References requiring control review</span></div>
      <div><strong>{detail?.records.total ?? "—"}</strong><span>Records for selected lineage</span></div>
    </div> : null}

    {tree && view === "hierarchy" ? <>
      <div className="dc-structure-toolbar">
        <label><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search code, title, type or hierarchy path" /></label>
        <div><button type="button" onClick={() => setExpanded(new Set(tree.items.map((item) => item.id)))}><ChevronDown size={14} /> Expand</button><button type="button" onClick={() => setExpanded(new Set(tree.items.filter((item) => item.depth < 1).map((item) => item.id)))}><ChevronRight size={14} /> Collapse</button></div>
      </div>
      <div className="dc-structure-workspace">
        <div className="dc-structure-workspace__browser">
          <div className="dc-structure-tree" role="tree" aria-label="Controlled document hierarchy">
            {rows.map((node) => {
              const Icon = nodeIcon(node.node_type);
              const childCount = childCounts.get(node.id) || 0;
              const open = expanded.has(node.id) || Boolean(search.trim());
              return <div className="dc-structure-node" role="treeitem" aria-level={node.depth + 1} aria-expanded={childCount ? open : undefined} aria-selected={selectedId === node.id} key={node.id}>
                <div className={`dc-structure-node__row${node.node_type === "ROOT" || node.node_type === "MANAGEMENT_SYSTEM" ? " is-group" : ""}${selectedId === node.id ? " is-selected" : ""}`} style={{ "--tree-depth": node.depth } as CSSProperties}>
                  <button type="button" className="dc-structure-node__toggle" disabled={!childCount || Boolean(search.trim())} aria-label={`${open ? "Collapse" : "Expand"} ${node.title}`} onClick={() => setExpanded((current) => { const next = new Set(current); if (next.has(node.id)) next.delete(node.id); else next.add(node.id); return next; })}>{childCount ? open ? <ChevronDown size={15} /> : <ChevronRight size={15} /> : <span />}</button>
                  <button type="button" className="dc-structure-node__primary" onClick={() => selectNode(node.id)}><Icon size={16} /><span><strong>{node.code} · {node.title}</strong><small>{nodeLabel(node)} · {childCount} child{childCount === 1 ? "" : "ren"}</small></span></button>
                  <div className="dc-structure-node__meta">{node.execution ? <span className="dc-structure-node__execution">{node.execution.submission_mode.replaceAll("_", " ")}</span> : null}<DocumentControlStatus status={node.document?.status || node.status} kind={statusKind(node.document?.status || node.status)} /></div>
                  <div className="dc-structure-node__actions">{node.manual_id ? <button type="button" aria-label={`Open ${node.code} document`} title="Open document" onClick={() => navigate(`${basePath}/library/${node.manual_id}`)}><BookOpen size={14} /></button> : null}<button type="button" aria-label={`Inspect ${node.code} lineage`} title="Inspect lineage" onClick={() => selectNode(node.id)}><GitBranch size={14} /></button></div>
                </div>
              </div>;
            })}
            {!rows.length ? <DocumentControlEmpty icon={Search} title="No matching structure node" message="Try a document code, title, type or a broader term." /> : null}
          </div>
        </div>
        <NodeInspector loading={detailLoading} error={detailError} detail={detail} basePath={basePath} onSelect={selectNode} onRetry={() => { if (selectedId) { setDetail(null); setDetailError(""); void getDocumentationNodeConnections(tenant, selectedId).then(setDetail).catch((caught) => setDetailError(caught instanceof Error ? caught.message : "The selected lineage could not be loaded.")); } }} />
      </div>
    </> : null}

    {tree && view === "references" ? <section className="dc-reference-monitor">
      <header><div><h2>Reference review queue</h2><p>Detected references remain proposals. Resolve and approve them in Compliance; this view preserves their position beside the controlled hierarchy.</p></div><button type="button" className="dc-button" onClick={() => navigate(`${basePath}/compliance?view=relationships`)}>Open compliance decisions <ExternalLink size={14} /></button></header>
      <div className="dc-reference-monitor__filters">{["", "UNRESOLVED", "OUTDATED", "BROKEN", "VERIFIED"].map((status) => <button type="button" key={status || "ALL"} className={referenceStatus === status ? "active" : ""} onClick={() => setReferenceStatus(status)}>{status || "All"}</button>)}</div>
      {referenceLoading ? <DocumentControlLoading label="Loading detected references…" /> : null}
      {referenceError ? <DocumentControlError message={referenceError} retry={() => void loadReferences()} /> : null}
      {!referenceLoading && !referenceError && referenceData ? <div className="dc-table-wrap"><table className="dc-table"><thead><tr><th>Source</th><th>Detected reference</th><th>Relationship</th><th>Status</th><th>Action</th></tr></thead><tbody>{referenceData.items.map((item) => <tr key={item.id}><td><strong>{item.source_manual.code}</strong><small>{item.source_manual.title}</small></td><td><strong>{item.raw_token}</strong><p>{item.source_context || "No extracted context"}</p></td><td>{item.relationship_type.replaceAll("_", " ")}</td><td><DocumentControlStatus status={item.status} kind={statusKind(item.status)} /></td><td><button type="button" className="dc-button" onClick={() => { const node = tree.items.find((candidate) => candidate.manual_id === item.source_manual.id); if (node) selectNode(node.id); }}>Show in structure</button></td></tr>)}</tbody></table>{!referenceData.items.length ? <DocumentControlEmpty icon={AlertTriangle} title="No references in this view" message="Change the status filter or reconcile controlled sources." /> : null}</div> : null}
    </section> : null}
  </DocumentControlShell>;
}
