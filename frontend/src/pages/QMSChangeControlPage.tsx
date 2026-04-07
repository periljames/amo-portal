import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { RefreshCw, Search, CheckCircle2, FileClock, XCircle } from "lucide-react";
import QMSLayout from "../components/QMS/QMSLayout";
import SectionCard from "../components/shared/SectionCard";
import DataTableShell from "../components/shared/DataTableShell";
import EmptyState from "../components/shared/EmptyState";
import InlineError from "../components/shared/InlineError";
import Button from "../components/UI/Button";
import { getContext } from "../services/auth";
import {
  qmsListChangeRequests,
  type QMSChangeRequestOut,
  type QMSChangeRequestStatus,
} from "../services/qms";

type LoadState = "idle" | "loading" | "ready" | "error";

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

const STATUS_OPTIONS: Array<{ value: QMSChangeRequestStatus | "ALL"; label: string }> = [
  { value: "ALL", label: "All statuses" },
  { value: "SUBMITTED", label: "Submitted" },
  { value: "UNDER_REVIEW", label: "Under review" },
  { value: "SUBMITTED_TO_AUTHORITY", label: "Submitted to authority" },
  { value: "APPROVED", label: "Approved" },
  { value: "REJECTED", label: "Rejected" },
  { value: "CANCELLED", label: "Cancelled" },
];

function statusTone(status: QMSChangeRequestStatus): string {
  if (status === "APPROVED") return "qms-pill qms-pill--success";
  if (status === "UNDER_REVIEW" || status === "SUBMITTED_TO_AUTHORITY") return "qms-pill qms-pill--warning";
  if (status === "REJECTED" || status === "CANCELLED") return "qms-pill qms-pill--danger";
  return "qms-pill qms-pill--info";
}

const QMSChangeControlPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [requests, setRequests] = useState<QMSChangeRequestOut[]>([]);
  const [statusFilter, setStatusFilter] = useState<QMSChangeRequestStatus | "ALL">("ALL");
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
    void load();
  }, [statusFilter]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return requests;
    return requests.filter((cr) => {
      return [cr.title, cr.reason, cr.status].filter(Boolean).join(" ").toLowerCase().includes(q);
    });
  }, [requests, search]);

  const metrics = useMemo(() => {
    const approved = requests.filter((item) => item.status === "APPROVED").length;
    const underReview = requests.filter((item) => item.status === "UNDER_REVIEW" || item.status === "SUBMITTED_TO_AUTHORITY").length;
    const rejected = requests.filter((item) => item.status === "REJECTED" || item.status === "CANCELLED").length;
    return [
      { label: "Visible requests", value: String(filtered.length), icon: FileClock },
      { label: "Approved", value: String(approved), icon: CheckCircle2 },
      { label: "Rejected or cancelled", value: String(rejected), icon: XCircle },
      { label: "Still under review", value: String(underReview), icon: RefreshCw },
    ];
  }, [filtered.length, requests]);

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Change Control"
      subtitle="Track approved changes to manuals, processes, and compliance requirements without wasting space on oversized controls."
      actions={
        <>
          <Button variant="secondary" onClick={() => navigate(-1)}>
            Back
          </Button>
          <Button onClick={load} loading={state === "loading"}>
            <RefreshCw size={16} />
            Refresh change control
          </Button>
        </>
      }
    >
      <div className="qms-page-grid">
        <SectionCard variant="subtle" className="qms-compact-toolbar-card">
          <div className="qms-toolbar qms-toolbar--portal">
            <label className="qms-field qms-field--compact">
              <span>Status</span>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as QMSChangeRequestStatus | "ALL")}
              >
                {STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="qms-field qms-field--grow qms-field--compact">
              <span>Search</span>
              <div className="qms-search-input">
                <Search size={16} />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search titles, reasons, or statuses"
                />
              </div>
            </label>
          </div>
        </SectionCard>

        <div className="portal-stat-grid">
          {metrics.map((item) => {
            const Icon = item.icon;
            return (
              <SectionCard key={item.label} variant="subtle" className="portal-stat-card">
                <div className="portal-stat-card__inner">
                  <span className="portal-stat-card__icon"><Icon size={18} /></span>
                  <div>
                    <p className="portal-stat-card__label">{item.label}</p>
                    <strong className="portal-stat-card__value">{item.value}</strong>
                  </div>
                </div>
              </SectionCard>
            );
          })}
        </div>

        <DataTableShell
          title="Change request register"
          actions={<span className="qms-table-meta">{filtered.length} item{filtered.length === 1 ? "" : "s"}</span>}
        >
          {state === "loading" ? <p className="qms-loading-copy">Loading change requests…</p> : null}
          {state === "error" ? <InlineError message={error || "Unable to load change requests."} onAction={() => void load()} /> : null}
          {state === "ready" ? (
            filtered.length ? (
              <div className="table-responsive">
                <table className="table table--portal">
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
                          <div className="table-primary-cell">
                            <strong>{cr.title}</strong>
                            <span>{cr.reason || "No summary provided."}</span>
                          </div>
                        </td>
                        <td>
                          <span className={statusTone(cr.status)}>{cr.status.replaceAll("_", " ")}</span>
                        </td>
                        <td>{formatDate(cr.requested_at)}</td>
                        <td>{formatDate(cr.updated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                title="No change requests match the selected filters"
                description="Try another status, clear the search, or refresh the register."
              />
            )
          ) : null}
        </DataTableShell>
      </div>
    </QMSLayout>
  );
};

export default QMSChangeControlPage;
