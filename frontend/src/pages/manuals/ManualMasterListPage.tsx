import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getMasterList } from "../../services/manuals";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";
import "./publicationsDashboard.css";

type PublicationMasterRow = {
  manual_id: string;
  code: string;
  title: string;
  current_revision?: string | null;
  current_issue_number?: string | null;
  current_status?: string | null;
  source_type?: string | null;
  page_count?: number | null;
  section_count?: number;
  pending_ack_count?: number;
};

export default function PublicationMasterListPage() {
  const { tenant, basePath } = useManualRouteContext();
  const [rows, setRows] = useState<PublicationMasterRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tenant) return;
    setLoading(true);
    getMasterList(tenant)
      .then((result) => setRows(result as PublicationMasterRow[]))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [tenant]);

  return (
    <ManualsPageLayout title="Publication Master List" subtitle="Controlled titles, current issue labels, formats, reader indexes, and acknowledgement state.">
      <div className="publications-table-wrap">
        <table className="publications-table">
          <thead><tr><th>Code</th><th>Publication</th><th>Issue / revision</th><th>Format</th><th>Reader index</th><th>Status</th><th>Pending acknowledgements</th></tr></thead>
          <tbody>
            {loading ? <tr><td colSpan={7}>Loading publication master list…</td></tr> : null}
            {!loading && rows.map((row) => (
              <tr key={row.manual_id}>
                <td><Link to={`${basePath}/${row.manual_id}`}><strong>{row.code}</strong></Link></td>
                <td>{row.title}</td>
                <td><span>Issue {row.current_issue_number || "—"}</span><small>Rev {row.current_revision || "—"}</small></td>
                <td><span>{row.source_type || "—"}</span>{row.page_count ? <small>{row.page_count} pages</small> : null}</td>
                <td>{row.section_count || 0} sections</td>
                <td>{String(row.current_status || "Unknown").replaceAll("_", " ")}</td>
                <td>{row.pending_ack_count || 0}</td>
              </tr>
            ))}
            {!loading && !rows.length ? <tr><td colSpan={7}>No controlled publications are registered.</td></tr> : null}
          </tbody>
        </table>
      </div>
    </ManualsPageLayout>
  );
}
