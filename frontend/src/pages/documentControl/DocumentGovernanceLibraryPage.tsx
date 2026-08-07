import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowUpDown, BookOpen, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { listGovernanceDocuments, type GovernanceLibraryResponse } from "../../services/documentGovernance";
import DocumentControlShell, { DocumentControlEmpty, DocumentControlError, DocumentControlLoading, DocumentControlStatus } from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentGovernance.css";

function statusKind(status: string): "success" | "warning" | "danger" | "info" | "neutral" {
  const value = status.toUpperCase();
  if (["PUBLISHED", "ACTIVE", "COMPLETED", "CURRENT"].includes(value)) return "success";
  if (["FAILED", "SUPERSEDED", "RESTRICTED", "BROKEN"].includes(value)) return "danger";
  if (["PENDING", "NOT_INDEXED", "DRAFT", "MATCH_PROPOSED"].includes(value)) return "warning";
  return "neutral";
}

export default function DocumentGovernanceLibraryPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<GovernanceLibraryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const values = useMemo(() => ({
    q: params.get("q") || undefined,
    document_type: params.get("document_type") || undefined,
    lifecycle_status: params.get("lifecycle_status") || undefined,
    control_status: params.get("control_status") || undefined,
    indexing_status: params.get("indexing_status") || undefined,
    unresolved_ownership: params.get("unresolved_ownership") === "true",
    unresolved_relationships: params.get("unresolved_relationships") === "true",
    superseded: params.has("superseded") ? params.get("superseded") === "true" : undefined,
    sort: params.get("sort") || "code",
    direction: params.get("direction") || "asc",
    page: Number(params.get("page") || 1),
    per_page: Number(params.get("per_page") || 50),
  }), [params]);

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    setError("");
    try {
      setData(await listGovernanceDocuments(tenant, values));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The governed library could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [tenant, values]);

  useEffect(() => { void load(); }, [load]);

  const update = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value); else next.delete(name);
    if (name !== "page") next.set("page", "1");
    setParams(next);
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.pagination.total / data.pagination.per_page)) : 1;

  return (
    <DocumentControlShell title="Controlled document library" eyebrow="GOVERNED ESTATE" subtitle="Server-bounded register with ownership, structure, relationship completeness and indexing state." canControl>
      <div className="dgov-library" data-testid="document-governance-library">
        <form className="dgov-filters" onSubmit={(event) => event.preventDefault()}>
          <label className="dgov-search"><Search size={16} /><input aria-label="Search documents" value={params.get("q") || ""} onChange={(event) => update("q", event.target.value)} placeholder="Code, title, filename or reference token" /></label>
          <select aria-label="Control status" value={params.get("control_status") || ""} onChange={(event) => update("control_status", event.target.value)}><option value="">All control states</option><option value="INTERNAL">Internal</option><option value="EXTERNAL">External</option><option value="RECORD">Record</option></select>
          <select aria-label="Indexing status" value={params.get("indexing_status") || ""} onChange={(event) => update("indexing_status", event.target.value)}><option value="">All indexing states</option><option value="COMPLETED">Indexed</option><option value="PENDING">Pending</option><option value="RUNNING">Running</option><option value="FAILED">Failed</option><option value="NOT_INDEXED">Not indexed</option></select>
          <label className="dgov-check"><input type="checkbox" checked={params.get("unresolved_ownership") === "true"} onChange={(event) => update("unresolved_ownership", event.target.checked ? "true" : "")} /> Ownership unresolved</label>
          <label className="dgov-check"><input type="checkbox" checked={params.get("unresolved_relationships") === "true"} onChange={(event) => update("unresolved_relationships", event.target.checked ? "true" : "")} /> Relationships unresolved</label>
        </form>
        {loading ? <DocumentControlLoading label="Loading bounded document register…" /> : null}
        {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
        {!loading && !error && data?.items.length ? (
          <div className="dgov-table-wrap">
            <table className="dgov-table">
              <thead><tr><th><button type="button" onClick={() => update("direction", values.direction === "asc" ? "desc" : "asc")}>Code / title <ArrowUpDown size={13} /></button></th><th>Revision</th><th>Ownership</th><th>Control</th><th>Relationships</th><th>Index</th><th>Action</th></tr></thead>
              <tbody>{data.items.map((item) => (
                <tr key={item.id} className={item.superseded ? "is-superseded" : ""}>
                  <td><strong>{item.code}</strong><span>{item.title}</span><small>{item.document_type}{item.structure_path ? ` · ${item.structure_path}` : " · Structure unresolved"}</small></td>
                  <td><strong>{item.issue_number ? `Issue ${item.issue_number} · ` : ""}Rev {item.revision_number || "—"}</strong><small>{item.effective_date || "Not effective"}</small></td>
                  <td>{item.owner ? <><strong>{item.owner.assignee.name}</strong><small>{item.owner.assignment_source} · {item.owner.confirmation_status}</small></> : <span className="dgov-warning"><AlertTriangle size={14} /> Owner missing</span>}{item.responsible_department ? <small>{item.responsible_department.assignee.name}</small> : null}</td>
                  <td><DocumentControlStatus status={item.control_status} kind={statusKind(item.control_status)} /><small>{item.lifecycle_status}</small></td>
                  <td><strong>{item.unresolved_relationships}</strong><small>awaiting resolution</small></td>
                  <td><DocumentControlStatus status={item.indexing_status} kind={statusKind(item.indexing_status)} /></td>
                  <td><button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library/${item.id}`)}><BookOpen size={14} /> Open</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : null}
        {!loading && !error && data && !data.items.length ? <DocumentControlEmpty title="No documents match" message="Adjust the URL-backed filters or reconcile existing documents to create governed metadata." /> : null}
        {data ? <footer className="dgov-pagination"><span>{data.pagination.total ? `${(data.pagination.page - 1) * data.pagination.per_page + 1}–${Math.min(data.pagination.page * data.pagination.per_page, data.pagination.total)} of ${data.pagination.total}` : "0 records"}</span><select aria-label="Rows per page" value={data.pagination.per_page} onChange={(event) => update("per_page", event.target.value)}><option value="25">25</option><option value="50">50</option><option value="100">100</option><option value="250">250</option></select><button type="button" disabled={data.pagination.page <= 1} onClick={() => update("page", String(data.pagination.page - 1))}><ChevronLeft size={16} /> Previous</button><span>Page {data.pagination.page} of {totalPages}</span><button type="button" disabled={data.pagination.page >= totalPages} onClick={() => update("page", String(data.pagination.page + 1))}>Next <ChevronRight size={16} /></button></footer> : null}
      </div>
    </DocumentControlShell>
  );
}
