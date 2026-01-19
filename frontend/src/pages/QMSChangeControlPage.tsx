import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import { getContext } from "../services/auth";
import {
  qmsListChangeRequests,
  type QMSChangeRequestOut,
  type QMSChangeRequestStatus,
} from "../services/qms";

type LoadState = "idle" | "loading" | "ready" | "error";

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

const STATUS_OPTIONS: Array<{ value: QMSChangeRequestStatus | "ALL"; label: string }> =
  [
    { value: "ALL", label: "All statuses" },
    { value: "SUBMITTED", label: "Submitted" },
    { value: "UNDER_REVIEW", label: "Under review" },
    { value: "SUBMITTED_TO_AUTHORITY", label: "Submitted to authority" },
    { value: "APPROVED", label: "Approved" },
    { value: "REJECTED", label: "Rejected" },
    { value: "CANCELLED", label: "Cancelled" },
  ];

const QMSChangeControlPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [requests, setRequests] = useState<QMSChangeRequestOut[]>([]);
  const [statusFilter, setStatusFilter] = useState<QMSChangeRequestStatus | "ALL">(
    "ALL"
  );
  const [search, setSearch] = useState("");

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const data = await qmsListChangeRequests({
        domain: "AMO",
        status_: statusFilter === "ALL" ? undefined : statusFilter,
      });
      setRequests(data);
      setState("ready");
    } catch (e: any) {
      setError(e?.message || "Failed to load change control register.");
      setState("error");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return requests;
    return requests.filter((cr) => cr.title.toLowerCase().includes(q));
  }, [requests, search]);

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Change Control"
      subtitle="Track approved changes to manuals, processes, and compliance requirements."
      actions={
        <button type="button" className="primary-chip-btn" onClick={load}>
          Refresh change control
        </button>
      }
    >
      <section className="qms-toolbar">
        <label className="qms-field">
          <span>Status</span>
          <select
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value as QMSChangeRequestStatus | "ALL")
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
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search change request titles"
          />
        </label>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(-1)}>
          Back
        </button>
      </section>

      {state === "loading" && (
        <div className="card card--info">
          <p>Loading change requests…</p>
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
                  <th>Change request</th>
                  <th>Status</th>
                  <th>Requested</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((cr) => (
                  <tr key={cr.id}>
                    <td>
                      <strong>{cr.title}</strong>
                      <div className="text-muted">{cr.reason || "No summary provided."}</div>
                    </td>
                    <td>
                      <span className="qms-pill">{cr.status}</span>
                    </td>
                    <td>{formatDate(cr.requested_at)}</td>
                    <td>{formatDate(cr.updated_at)}</td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={4} className="text-muted">
                      No change requests match the selected filters.
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

export default QMSChangeControlPage;
