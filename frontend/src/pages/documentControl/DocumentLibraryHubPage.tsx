import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Archive,
  BookOpen,
  Boxes,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Copy,
  FileCheck2,
  FileText,
  FilterX,
  FolderTree,
  Link2,
  Search,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  listIntegratedLibrary,
  type IntegratedLibraryFilters,
  type IntegratedLibraryItem,
  type IntegratedLibraryResponse,
} from "../../services/documentLibrary";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentLibrary.css";

const CATEGORIES = [
  ["", "All", BookOpen],
  ["POLICY", "Policies", ShieldCheck],
  ["MANUAL", "Manuals", BookOpen],
  ["PROCEDURE", "Procedures", Workflow],
  ["WORK_INSTRUCTION", "Work instructions", ClipboardCheck],
  ["FORM", "Forms", FileText],
  ["CHECKLIST", "Checklists", FileCheck2],
  ["REGISTER", "Registers", Archive],
  ["EXTERNAL_DOCUMENT", "External data", Boxes],
] as const;

function statusKind(status?: string | null): "success" | "warning" | "danger" | "info" | "neutral" {
  const value = String(status || "").toUpperCase();
  if (["PUBLISHED", "ACTIVE", "CURRENT", "RETURNED"].includes(value)) return "success";
  if (["SUPERSEDED", "ARCHIVED", "WITHDRAWN", "OVERDUE", "RECALLED"].includes(value)) return "danger";
  if (["DRAFT", "PENDING", "UNVERIFIED", "ISSUED"].includes(value)) return "warning";
  return "neutral";
}

function revisionText(item: IntegratedLibraryItem): string {
  const revision = item.latest_revision;
  if (!revision) return "No revision";
  return `${revision.issue_number ? `Issue ${revision.issue_number} · ` : ""}Rev ${revision.revision_number}`;
}

function physicalText(item: IntegratedLibraryItem): string {
  const physical = item.library.physical;
  if (!physical.total) return "No physical copy";
  const parts = [];
  if (physical.on_shelf) parts.push(`${physical.on_shelf} on shelf`);
  if (physical.checked_out) parts.push(`${physical.checked_out} with staff`);
  if (physical.recalled) parts.push(`${physical.recalled} recalled`);
  return parts.join(" · ") || `${physical.total} registered`;
}

function truthy(value: string | null): boolean {
  return value === "1" || value?.toLowerCase() === "true";
}

function queueLabel(params: URLSearchParams): string | null {
  if (truthy(params.get("unresolved_ownership"))) return "Ownership requiring confirmation";
  if (truthy(params.get("unresolved_relationships"))) return "Document relationships requiring review";
  if (params.get("indexing_status")) return `Indexing status: ${params.get("indexing_status")?.replaceAll("_", " ")}`;
  if (params.get("structure_status")) return `Structure status: ${params.get("structure_status")?.replaceAll("_", " ")}`;
  if (truthy(params.get("superseded_referenced"))) return "Superseded documents still referenced";
  if (params.get("owner_user_id")) return "Filtered by document owner";
  if (params.get("department_id")) return "Filtered by responsible department";
  return null;
}

export default function DocumentLibraryHubPage() {
  const navigate = useNavigate();
  const { tenant, basePath, readerBasePath } = useDocumentControlRoute();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<IntegratedLibraryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const filters = useMemo<IntegratedLibraryFilters>(() => ({
    q: params.get("q") || undefined,
    nodeType: params.get("type") || undefined,
    documentClass: params.get("class") || params.get("control_status") || undefined,
    status: params.get("status") || params.get("lifecycle_status") || undefined,
    ownerUserId: params.get("owner_user_id") || undefined,
    departmentId: params.get("department_id") || undefined,
    indexingStatus: params.get("indexing_status") || undefined,
    unresolvedOwnership: truthy(params.get("unresolved_ownership")),
    unresolvedRelationships: truthy(params.get("unresolved_relationships")),
    structureStatus: params.get("structure_status") || undefined,
    supersededReferenced: truthy(params.get("superseded_referenced")),
    sort: (params.get("sort") as IntegratedLibraryFilters["sort"]) || "code",
    direction: (params.get("direction") as IntegratedLibraryFilters["direction"]) || "asc",
    page: Math.max(1, Number(params.get("page") || 1)),
    perPage: Math.min(100, Math.max(25, Number(params.get("per_page") || 50))),
  }), [params]);

  const activeQueue = useMemo(() => queueLabel(params), [params]);

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    setError("");
    try {
      setData(await listIntegratedLibrary(tenant, filters));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The controlled library could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [filters, tenant]);

  useEffect(() => { void load(); }, [load]);

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.set("page", "1");
    setParams(next);
  };

  const updateSort = (value: string) => {
    const [sort, direction] = value.split(":");
    const next = new URLSearchParams(params);
    next.set("sort", sort || "code");
    next.set("direction", direction || "asc");
    next.set("page", "1");
    setParams(next);
  };

  const clearGovernanceQueue = () => {
    const next = new URLSearchParams(params);
    [
      "unresolved_ownership",
      "unresolved_relationships",
      "indexing_status",
      "structure_status",
      "superseded_referenced",
      "owner_user_id",
      "department_id",
    ].forEach((key) => next.delete(key));
    next.set("page", "1");
    setParams(next);
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.pagination.total / data.pagination.per_page)) : 1;
  const canControl = Boolean(data?.capabilities.control);

  const openReader = (item: IntegratedLibraryItem) => {
    const revisionId = item.read_target?.revision_id;
    if (!revisionId) return;
    navigate(`${readerBasePath}/${item.id}/rev/${revisionId}/read`);
  };

  return <DocumentControlShell
    title="Company document library"
    eyebrow="CONTROLLED INFORMATION"
    subtitle="One governed library for policies, manuals, procedures, work instructions, forms, registers, external technical data and their retained evidence."
    canControl={canControl}
    actions={<>
      <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/structure`)}><FolderTree size={14} /> Full tree</button>
      {canControl ? <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/records`)}><Archive size={14} /> Generated records</button> : null}
      {canControl ? <button type="button" className="dc-button dc-button--primary" onClick={() => navigate(`${basePath}/controlled-copies`)}><Copy size={14} /> Physical library</button> : null}
    </>}
  >
    <section className="dlibrary" data-testid="integrated-document-library">
      {activeQueue ? <div className="dlibrary__queue-filter" role="status"><span><ShieldCheck size={15} /><strong>Governance queue</strong> · {activeQueue}</span><button type="button" onClick={clearGovernanceQueue}><FilterX size={14} /> Clear queue filter</button></div> : null}

      <div className="dlibrary__categories" aria-label="Document categories">
        {CATEGORIES.map(([value, label, Icon]) => {
          const active = (filters.nodeType || "") === value;
          const count = value ? Number(data?.facets.node_types[value] || 0) : Number(data?.facets.visible_documents || 0);
          return <button key={label} type="button" className={active ? "active" : ""} onClick={() => update("type", value)}>
            <Icon size={16} /><span>{label}</span><small>{count}</small>
          </button>;
        })}
      </div>

      <div className="dlibrary__toolbar">
        <label className="dlibrary__search"><Search size={16} /><input value={params.get("q") || ""} onChange={(event) => update("q", event.target.value)} placeholder="Find code, title, source filename, form or work instruction" /></label>
        <select aria-label="Document control class" value={filters.documentClass || ""} onChange={(event) => update("class", event.target.value)}>
          <option value="">Internal + external</option><option value="INTERNAL">Internal controlled</option><option value="EXTERNAL">External controlled</option><option value="RECORD">Record documents</option>
        </select>
        <select aria-label="Document lifecycle" value={filters.status || ""} onChange={(event) => update("status", event.target.value)}>
          <option value="">All lifecycle states</option><option value="ACTIVE">Active</option><option value="SUPERSEDED">Superseded</option><option value="ARCHIVED">Archived</option>
        </select>
        <select aria-label="Sort company library" value={`${filters.sort || "code"}:${filters.direction || "asc"}`} onChange={(event) => updateSort(event.target.value)}>
          <option value="code:asc">Code A–Z</option><option value="code:desc">Code Z–A</option><option value="title:asc">Title A–Z</option><option value="title:desc">Title Z–A</option><option value="type:asc">Document type</option><option value="status:asc">Lifecycle status</option>
        </select>
      </div>

      {loading ? <DocumentControlLoading label="Opening the company library…" /> : null}
      {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {!loading && !error && data && !data.items.length ? <DocumentControlEmpty icon={BookOpen} title="No document matches this shelf" message="Change the category or search text. Access-controlled documents are shown only to permitted users." /> : null}

      {!loading && !error && data?.items.length ? <div className="dlibrary__table-wrap"><table className="dc-table dlibrary__table">
        <thead><tr><th>Document</th><th>Current issue</th><th>Owner</th><th>Availability</th><th>Connected evidence</th><th>Source / currency</th><th>Open</th></tr></thead>
        <tbody>{data.items.map((item) => {
          const physical = item.library.physical;
          const integration = item.library.integrations;
          const external = item.library.external;
          return <tr key={item.id}>
            <td><strong>{item.code}</strong><span>{item.title}</span><small>{item.library.node_type.replaceAll("_", " ")}{item.library.structure_path ? ` · ${item.library.structure_path}` : ""}</small></td>
            <td><strong>{revisionText(item)}</strong><small>{item.latest_revision?.effective_date || "No effective date"}</small><DocumentControlStatus status={item.read_target.kind} kind={item.read_target.uncontrolled ? "warning" : "success"} /></td>
            <td>{item.library.owner?.assignee?.name ? <><strong>{item.library.owner.assignee.name}</strong><small>{item.library.responsible_department?.assignee?.name || item.profile.owner_department}</small></> : <><strong>{item.profile.owner_department || item.owner_role}</strong><small>Named owner not resolved</small></>}</td>
            <td><div className="dlibrary__availability"><span><BookOpen size={14} /> Digital {item.read_target.revision_id ? "available" : "unavailable"}</span><span className={physical.overdue ? "is-danger" : ""}><Copy size={14} /> {physicalText(item)}</span>{physical.overdue ? <small>{physical.overdue} overdue return{physical.overdue === 1 ? "" : "s"}</small> : null}</div></td>
            <td>{canControl ? <div className="dlibrary__connections"><span><Link2 size={14} /> {item.library.semantic_relationships || 0} document links</span><span><Workflow size={14} /> {integration?.count || 0} module links</span><span><Archive size={14} /> {item.library.generated_records || 0} generated records</span>{integration?.modules?.length ? <small>{integration.modules.join(" · ")}</small> : null}</div> : <small>Open the document to follow permitted links.</small>}</td>
            <td>{external ? <><strong>{external.provider}</strong><DocumentControlStatus status={external.currency_status} kind={statusKind(external.currency_status)} /><small>{external.revision_label || "Revision not received"}{external.authority ? ` · ${external.authority}` : ""}</small></> : <><DocumentControlStatus status={item.profile.document_class} kind={statusKind(item.profile.document_class)} /><small>Company-controlled source</small></>}</td>
            <td><div className="dlibrary__actions"><button type="button" className="dc-button dc-button--primary" disabled={!item.read_target.revision_id} onClick={() => openReader(item)}><BookOpen size={14} /> Read</button>{canControl ? <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library/${item.id}`)}>Manage</button> : null}</div></td>
          </tr>;
        })}</tbody>
      </table></div> : null}

      {data ? <footer className="dlibrary__pagination">
        <span>{data.pagination.total ? `${(data.pagination.page - 1) * data.pagination.per_page + 1}–${Math.min(data.pagination.page * data.pagination.per_page, data.pagination.total)} of ${data.pagination.total}` : "0 documents"}</span>
        <select value={data.pagination.per_page} onChange={(event) => update("per_page", event.target.value)} aria-label="Documents per page"><option value="25">25</option><option value="50">50</option><option value="100">100</option></select>
        <button type="button" disabled={data.pagination.page <= 1} onClick={() => update("page", String(data.pagination.page - 1))}><ChevronLeft size={15} /> Previous</button>
        <span>Page {data.pagination.page} of {totalPages}</span>
        <button type="button" disabled={data.pagination.page >= totalPages} onClick={() => update("page", String(data.pagination.page + 1))}>Next <ChevronRight size={15} /></button>
      </footer> : null}
    </section>
  </DocumentControlShell>;
}
