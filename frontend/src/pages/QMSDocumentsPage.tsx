import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import { getContext } from "../services/auth";
import {
  qmsListDocuments,
  type QMSDocumentOut,
  type QMSDocumentStatus,
} from "../services/qms";

type LoadState = "idle" | "loading" | "ready" | "error";

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

const STATUS_OPTIONS: Array<{ value: QMSDocumentStatus | "ALL"; label: string }> =
  [
    { value: "ALL", label: "All statuses" },
    { value: "ACTIVE", label: "Active" },
    { value: "DRAFT", label: "Draft" },
    { value: "OBSOLETE", label: "Obsolete" },
  ];

const QMSDocumentsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<QMSDocumentOut[]>([]);

  const [statusFilter, setStatusFilter] = useState<QMSDocumentStatus | "ALL">(
    "ALL"
  );
  const [query, setQuery] = useState("");

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const docs = await qmsListDocuments({
        domain: "AMO",
        status_: statusFilter === "ALL" ? undefined : statusFilter,
        q: query.trim() || undefined,
      });
      setDocuments(docs);
      setState("ready");
    } catch (e: any) {
      setError(e?.message || "Failed to load document register.");
      setState("error");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return documents;
    return documents.filter(
      (doc) =>
        doc.title.toLowerCase().includes(q) ||
        doc.doc_code.toLowerCase().includes(q) ||
        doc.doc_type.toLowerCase().includes(q)
    );
  }, [documents, query]);

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Document Control"
      subtitle="Maintain controlled manuals, procedures, and revisions with acknowledgements."
      actions={
        <button type="button" className="primary-chip-btn" onClick={load}>
          Refresh documents
        </button>
      }
    >
      <section className="qms-toolbar">
        <label className="qms-field">
          <span>Status</span>
          <select
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value as QMSDocumentStatus | "ALL")
            }
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="qms-field qms-field--grow">
          <span>Search</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find document code, title, or type"
          />
        </label>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(-1)}>
          Back
        </button>
      </section>

      {state === "loading" && (
        <div className="card card--info">
          <p>Loading controlled documents…</p>
        </div>
      )}

      {state === "error" && (
        <div className="card card--error">
          <p>{error}</p>
          <button type="button" className="primary-chip-btn" onClick={load}>
            Retry
          </button>
        </div>
      )}

      {state === "ready" && (
        <div className="qms-card">
          <div className="table-responsive">
            <table className="table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Title</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Effective</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      <strong>{doc.doc_code}</strong>
                    </td>
                    <td>{doc.title}</td>
                    <td>{doc.doc_type}</td>
                    <td>
                      <span className="qms-pill">{doc.status}</span>
                    </td>
                    <td>{formatDate(doc.effective_date)}</td>
                    <td>{formatDate(doc.updated_at)}</td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-muted">
                      No documents match the selected filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </QMSLayout>
  );
};

export default QMSDocumentsPage;
