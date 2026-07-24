import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, FilePlus2, Search, ShieldAlert } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  listDocumentControlDocuments,
  type DocumentLibraryItem,
  type DocumentLibraryResponse,
} from "../../services/documentControl";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
  useDocumentControlRoute,
} from "./DocumentControlShell";

function statusKind(document: DocumentLibraryItem): "success" | "warning" | "danger" | "neutral" {
  if (document.read_target.kind === "PUBLISHED") return "success";
  if (document.read_target.kind === "UNCONTROLLED") return "warning";
  if (!document.latest_revision) return "danger";
  return "neutral";
}

export default function DocumentControlLibraryPage() {
  const navigate = useNavigate();
  const { tenant, basePath, readerBasePath } = useDocumentControlRoute();
  const [response, setResponse] = useState<DocumentLibraryResponse | null>(null);
  const [query, setQuery] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    setError("");
    try {
      setResponse(await listDocumentControlDocuments(tenant, {
        q: query.trim() || undefined,
        documentClass: classFilter || undefined,
        perPage: 100,
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The document library could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [classFilter, query, tenant]);

  useEffect(() => {
    const handle = window.setTimeout(() => void load(), query ? 260 : 0);
    return () => window.clearTimeout(handle);
  }, [load, query]);

  const documents = response?.items || [];
  const canControl = useMemo(() => documents.some((row) => row.read_target.kind === "UNCONTROLLED" || Boolean(row.workflow)), [documents]);

  const openPrimary = (document: DocumentLibraryItem) => {
    if (document.read_target.revision_id) {
      navigate(`${readerBasePath}/${document.id}/rev/${document.read_target.revision_id}/read`);
      return;
    }
    navigate(`${basePath}/library/${document.id}`);
  };

  return (
    <DocumentControlShell
      title="Library"
      subtitle="One searchable register for internal manuals, external technical data, and controlled records. The primary action always opens the permitted revision directly."
      canControl={canControl}
      actions={canControl ? <button type="button" className="dc-button dc-button--primary" onClick={() => navigate(`/maintenance/${tenant}/publications?upload=1`)}><FilePlus2 size={15} /> Register or upload</button> : undefined}
    >
      <div className="dc-toolbar">
        <label className="dc-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search code, title, category, or status" /></label>
        <label className="dc-search" style={{ minWidth: "12rem" }}>
          <select value={classFilter} onChange={(event) => setClassFilter(event.target.value)} aria-label="Document class">
            <option value="">All document classes</option>
            <option value="INTERNAL">Internal controlled</option>
            <option value="EXTERNAL">External technical data</option>
            <option value="RECORD">Records and evidence</option>
          </select>
        </label>
      </div>

      {loading ? <DocumentControlLoading label="Loading the controlled library…" /> : null}
      {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {!loading && !error && documents.length ? (
        <div className="dc-table-wrap">
          <table className="dc-table">
            <thead><tr><th>Code</th><th>Document</th><th>Revision available</th><th>Governance</th><th>Work</th><th>Action</th></tr></thead>
            <tbody>{documents.map((document) => (
              <tr key={document.id} className="dc-row--clickable" tabIndex={0} onClick={() => openPrimary(document)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") openPrimary(document); }}>
                <td><strong>{document.code}</strong><small>{document.profile.document_class.replaceAll("_", " ")}</small></td>
                <td><strong>{document.title}</strong><small>{document.manual_type} · {document.profile.owner_department}</small></td>
                <td>
                  <strong>{document.latest_revision ? `Issue ${document.latest_revision.issue_number || "—"} · Rev ${document.latest_revision.revision_number}` : "No revision uploaded"}</strong>
                  <small>{document.latest_revision?.source_type || "No source"}{document.latest_revision?.source_page_count ? ` · ${document.latest_revision.source_page_count} pages` : ""}</small>
                </td>
                <td>
                  <DocumentControlStatus
                    status={document.read_target.kind === "PUBLISHED" ? "Effective publication" : document.read_target.kind === "UNCONTROLLED" ? "Uncontrolled draft" : document.latest_revision?.status || "No revision"}
                    kind={statusKind(document)}
                  />
                  <small>{document.profile.regulated_flag ? "Regulated" : "Internal control"}{document.profile.restricted_flag ? " · Restricted" : ""}</small>
                </td>
                <td><strong>{document.open_change_requests} changes</strong><small>{document.pending_acknowledgements} acknowledgements pending</small></td>
                <td>
                  <button type="button" className="dc-button dc-button--primary" onClick={(event) => { event.stopPropagation(); openPrimary(document); }}>
                    <BookOpen size={14} /> {document.read_target.label}
                  </button>
                  <button type="button" className="dc-button" style={{ marginTop: "0.35rem" }} onClick={(event) => { event.stopPropagation(); navigate(`${basePath}/library/${document.id}`); }}>View record</button>
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ) : null}

      {!loading && !error && !documents.length ? (
        <DocumentControlEmpty
          icon={query || classFilter ? Search : ShieldAlert}
          title={query || classFilter ? "No document matches the current search" : "No document has been registered"}
          message={query || classFilter ? "Clear the search or select another document class." : "A Document Control user must upload or register the first document before staff can read it."}
          action={(query || classFilter) ? <button type="button" className="dc-button" onClick={() => { setQuery(""); setClassFilter(""); }}>Clear filters</button> : undefined}
        />
      ) : null}
    </DocumentControlShell>
  );
}
