import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, FolderOpen, Search, UploadCloud } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getMasterList,
  listFeaturedManuals,
  listManuals,
  subscribeManualsUpdated,
  type ManualFeaturedEntry,
  type ManualSummary,
} from "../../services/manuals";
import { getCachedUser } from "../../services/auth";
import ControlledDocumentUploadDialog from "../../components/documentControl/ControlledDocumentUploadDialog";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";
import "./manualsDashboard.css";
import "./publicationsDashboard.css";

type MasterRow = {
  manual_id: string;
  code: string;
  title: string;
  manual_type?: string;
  current_revision: string | null;
  current_status: string;
  current_issue_number?: string | null;
  current_effective_date?: string | null;
  pending_ack_count: number;
  source_type?: string | null;
  source_filename?: string | null;
  page_count?: number | null;
  section_count?: number;
  block_count?: number;
};

function canWritePublications(): boolean {
  const user = getCachedUser();
  const role = String(user?.role || "");
  return user?.module_access?.documents === "manage"
    && ["QUALITY_MANAGER", "QUALITY_OFFICER", "DOCUMENT_CONTROL_OFFICER"].includes(role);
}

export default function PublicationsDashboardPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useManualRouteContext();
  const canWrite = canWritePublications();
  const [manuals, setManuals] = useState<ManualSummary[]>([]);
  const [masterRows, setMasterRows] = useState<MasterRow[]>([]);
  const [featured, setFeatured] = useState<ManualFeaturedEntry[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);

  const refresh = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    const [manualRows, master, featuredRows] = await Promise.all([
      listManuals(tenant).catch(() => []),
      getMasterList(tenant).catch(() => []),
      listFeaturedManuals(tenant).catch(() => []),
    ]);
    setManuals(manualRows);
    setMasterRows(master as MasterRow[]);
    setFeatured(featuredRows);
    setLoading(false);
  }, [tenant]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    if (!tenant) return;
    return subscribeManualsUpdated((detail) => {
      if (detail.tenantSlug === tenant) void refresh();
    });
  }, [refresh, tenant]);

  const manualById = useMemo(() => new Map(manuals.map((manual) => [manual.id, manual])), [manuals]);
  const rows = useMemo(() => {
    const masterById = new Map(masterRows.map((row) => [row.manual_id, row]));
    return manuals.map((manual) => {
      const master = masterById.get(manual.id);
      return {
        ...manual,
        current_revision_label: master?.current_revision || null,
        current_revision_id: manual.current_published_rev_id,
        current_status: master?.current_status || manual.status,
        current_issue_number: master?.current_issue_number || null,
        pending_ack_count: master?.pending_ack_count || 0,
        source_type: master?.source_type || null,
        page_count: master?.page_count || null,
        section_count: master?.section_count || 0,
        block_count: master?.block_count || 0,
      };
    });
  }, [manuals, masterRows]);

  const filteredRows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) => [row.code, row.title, row.manual_type, row.current_status].some((value) => String(value || "").toLowerCase().includes(needle)));
  }, [query, rows]);

  const openPublication = (manualId: string, revisionId?: string | null) => {
    if (revisionId) navigate(`${basePath}/${manualId}/rev/${revisionId}/read`);
    else navigate(`${basePath}/${manualId}`);
  };

  return (
    <ManualsPageLayout
      title="Publications"
      subtitle="Controlled manuals, legislation, procedures, forms, and technical publications in one searchable library."
      actions={canWrite ? (
        <button type="button" className="manuals-primary-btn" onClick={() => setUploadOpen(true)}><UploadCloud size={16} /> Upload publications</button>
      ) : undefined}
    >
      <section className="publications-overview-strip" aria-label="Publication summary">
        <div><strong>{rows.length}</strong><span>Controlled titles</span></div>
        <div><strong>{rows.filter((row) => row.current_revision_id).length}</strong><span>Published revisions</span></div>
        <div><strong>{masterRows.reduce((sum, row) => sum + Number(row.pending_ack_count || 0), 0)}</strong><span>Pending acknowledgements</span></div>
        <div><strong>{masterRows.filter((row) => row.source_type === "PDF").length}</strong><span>PDF sources</span></div>
      </section>

      {featured.length ? (
        <section className="publications-featured" aria-label="Frequently used publications">
          <div className="publications-section-heading"><div><h2>Frequently used</h2><p>Open the current controlled revision without searching the register.</p></div></div>
          <div className="publications-featured-grid">
            {featured.map((item) => {
              const manual = manualById.get(item.manual_id);
              return (
                <button type="button" key={item.manual_id} onClick={() => openPublication(item.manual_id, manual?.current_published_rev_id)}>
                  <BookOpen size={18} />
                  <span><strong>{item.code}</strong><small>{item.title}</small></span>
                  <em>{item.open_count} opens</em>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}

      <section className="publications-register">
        <div className="publications-register__toolbar">
          <div><h2>Publication register</h2><p>Only revision IDs returned by the API are used to open the reader; revision labels are never treated as record identifiers.</p></div>
          <label className="publications-register__search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search code, title, type, or status" /></label>
        </div>
        <div className="publications-table-wrap">
          <table className="publications-table">
            <thead><tr><th>Code</th><th>Publication</th><th>Issue / revision</th><th>Format</th><th>Reader index</th><th>Status</th><th /></tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={7}>Loading publication register…</td></tr> : null}
              {!loading && filteredRows.map((row) => (
                <tr key={row.id}>
                  <td><strong>{row.code}</strong></td>
                  <td><span>{row.title}</span><small>{row.manual_type}</small></td>
                  <td><span>Issue {row.current_issue_number || "—"}</span><small>Rev {row.current_revision_label || "—"}</small></td>
                  <td>{row.source_type || "—"}{row.page_count ? <small>{row.page_count} pages</small> : null}</td>
                  <td><span>{row.section_count} sections</span><small>{row.block_count} text blocks</small></td>
                  <td><span className={`publications-status status-${String(row.current_status || "unknown").toLowerCase()}`}>{String(row.current_status || "Unknown").replaceAll("_", " ")}</span>{row.pending_ack_count ? <small>{row.pending_ack_count} ack pending</small> : null}</td>
                  <td><button type="button" className="publications-open-button" onClick={() => openPublication(row.id, row.current_revision_id)}><FolderOpen size={15} /> {row.current_revision_id ? "Open reader" : "View record"}</button></td>
                </tr>
              ))}
              {!loading && !filteredRows.length ? <tr><td colSpan={7}>No publication matches the current search.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>

      <ControlledDocumentUploadDialog
        tenant={tenant}
        open={uploadOpen}
        allowApprovedIntake
        onClose={() => setUploadOpen(false)}
        onUploaded={async (result) => {
          await refresh();
          navigate(`${basePath}/${result.manual_id}/rev/${result.revision_id}/read`);
        }}
      />
    </ManualsPageLayout>
  );
}
