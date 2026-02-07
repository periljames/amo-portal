import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import AuditHistoryPanel from "../components/QMS/AuditHistoryPanel";
import { getContext } from "../services/auth";
import {
  qmsListAudits,
  type QMSAuditOut,
  type QMSAuditStatus,
} from "../services/qms";

type LoadState = "idle" | "loading" | "ready" | "error";

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

const STATUS_OPTIONS: Array<{ value: QMSAuditStatus | "ALL"; label: string }> =
  [
    { value: "ALL", label: "All statuses" },
    { value: "PLANNED", label: "Planned" },
    { value: "IN_PROGRESS", label: "In progress" },
    { value: "CAP_OPEN", label: "CAP open" },
    { value: "CLOSED", label: "Closed" },
  ];

const QMSAuditsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [audits, setAudits] = useState<QMSAuditOut[]>([]);
  const [statusFilter, setStatusFilter] = useState<QMSAuditStatus | "ALL">(
    "ALL"
  );
  const [search, setSearch] = useState("");

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const data = await qmsListAudits({
        domain: "AMO",
        status_: statusFilter === "ALL" ? undefined : statusFilter,
      });
      setAudits(data);
      setState("ready");
    } catch (e: any) {
      setError(e?.message || "Failed to load audit programme.");
      setState("error");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return audits;
    return audits.filter(
      (audit) =>
        audit.title.toLowerCase().includes(q) ||
        audit.audit_ref.toLowerCase().includes(q) ||
        audit.kind.toLowerCase().includes(q)
    );
  }, [audits, search]);

  const upcoming = filtered
    .filter((audit) => audit.planned_start && new Date(audit.planned_start) > new Date())
    .sort((a, b) => new Date(a.planned_start || "").getTime() - new Date(b.planned_start || "").getTime())
    .slice(0, 6);

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Audits & Inspections"
      subtitle="Plan, execute, and close quality audits with compliance visibility."
      actions={
        <button type="button" className="primary-chip-btn" onClick={load}>
          Refresh audits
        </button>
      }
    >
      <section className="qms-toolbar">
        <label className="qms-field">
          <span>Status</span>
          <select
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value as QMSAuditStatus | "ALL")
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
            placeholder="Search audit title, reference, or type"
          />
        </label>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(-1)}>
          Back
        </button>
      </section>

      <section className="qms-grid">
        <div className="qms-card">
          <div className="qms-card__header">
            <div>
              <h3 className="qms-card__title">Next up</h3>
              <p className="qms-card__subtitle">
                Immediate audit plan for the coming weeks.
              </p>
            </div>
          </div>
          <div className="qms-list">
            {upcoming.map((audit) => (
              <div key={audit.id} className="qms-list__item">
                <div>
                  <strong>{audit.title}</strong>
                  <span className="qms-list__meta">
                    {audit.audit_ref} · {audit.kind}
                  </span>
                </div>
                <span className="qms-pill qms-pill--info">
                  {formatDate(audit.planned_start)}
                </span>
              </div>
            ))}
            {upcoming.length === 0 && (
              <p className="text-muted">No upcoming audits scheduled.</p>
            )}
          </div>
        </div>

        <div className="qms-card qms-card--wide">
          {state === "loading" && (
            <div className="card card--info">
              <p>Loading audits…</p>
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
            <div className="table-responsive">
              <table className="table">
                <thead>
                  <tr>
                    <th>Audit</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Start</th>
                    <th>End</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((audit) => (
                    <tr key={audit.id}>
                      <td>
                        <strong>{audit.title}</strong>
                        <div className="text-muted">{audit.audit_ref}</div>
                      </td>
                      <td>{audit.kind}</td>
                      <td>
                        <span className="qms-pill">{audit.status}</span>
                      </td>
                      <td>{formatDate(audit.planned_start)}</td>
                      <td>{formatDate(audit.planned_end)}</td>
                    </tr>
                  ))}
                  {filtered.length === 0 && (
                    <tr>
                      <td colSpan={5} className="text-muted">
                        No audits match the selected filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <section className="qms-grid">
        <AuditHistoryPanel title="Audit programme history" entityType="qms_audit" />
      </section>
    </QMSLayout>
  );
};

export default QMSAuditsPage;
