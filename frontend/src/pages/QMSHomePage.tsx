// src/pages/quality/QMSHomePage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getContext } from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";
import {
  qmsListAudits,
  qmsListChangeRequests,
  qmsListDistributions,
  qmsListDocuments,
  type QMSAuditOut,
  type QMSChangeRequestOut,
  type QMSDistributionOut,
  type QMSDocumentOut,
} from "../services/qms";

type LoadState = "idle" | "loading" | "ready" | "error";

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

function isWithinDays(dateStr: string | null, days: number): boolean {
  if (!dateStr) return false;
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  const limit = new Date();
  limit.setDate(now.getDate() + days);
  return d >= now && d <= limit;
}

function niceDomain(domain?: string): string {
  switch ((domain || "").toUpperCase()) {
    case "AMO":
      return "AMO";
    case "AOC":
      return "AOC";
    case "SMS":
      return "SMS";
    default:
      return domain || "All";
  }
}

const QMSHomePage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const amoDisplay = amoSlug !== "UNKNOWN" ? decodeAmoCertFromUrl(amoSlug) : "AMO";

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);

  const [documents, setDocuments] = useState<QMSDocumentOut[]>([]);
  const [distributions, setDistributions] = useState<QMSDistributionOut[]>([]);
  const [changeRequests, setChangeRequests] = useState<QMSChangeRequestOut[]>([]);
  const [audits, setAudits] = useState<QMSAuditOut[]>([]);

  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      // For now we scope to AMO by default. You can widen later.
      const domain = "AMO";

      const [docs, dists, crs, auds] = await Promise.all([
        qmsListDocuments({ domain }),
        qmsListDistributions({ outstanding_only: true }),
        qmsListChangeRequests({ domain }),
        qmsListAudits({ domain }),
      ]);

      setDocuments(docs);
      setDistributions(dists);
      setChangeRequests(crs);
      setAudits(auds);
      setLastRefreshedAt(new Date());
      setState("ready");
    } catch (e: any) {
      setState("error");
      setError(e?.message || "Failed to load QMS overview.");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const metrics = useMemo(() => {
    const docCounts = {
      ACTIVE: documents.filter((d) => d.status === "ACTIVE").length,
      DRAFT: documents.filter((d) => d.status === "DRAFT").length,
      OBSOLETE: documents.filter((d) => d.status === "OBSOLETE").length,
    };

    const auditCounts = {
      PLANNED: audits.filter((a) => a.status === "PLANNED").length,
      IN_PROGRESS: audits.filter((a) => a.status === "IN_PROGRESS").length,
      CAP_OPEN: audits.filter((a) => a.status === "CAP_OPEN").length,
      CLOSED: audits.filter((a) => a.status === "CLOSED").length,
      UPCOMING_30D: audits.filter((a) => isWithinDays(a.planned_start, 30)).length,
    };

    const openCR = changeRequests.filter((cr) =>
      ["SUBMITTED", "UNDER_REVIEW", "SUBMITTED_TO_AUTHORITY"].includes(cr.status)
    );

    const crCounts = {
      OPEN: openCR.length,
      APPROVED: changeRequests.filter((cr) => cr.status === "APPROVED").length,
      REJECTED: changeRequests.filter((cr) => cr.status === "REJECTED").length,
      CANCELLED: changeRequests.filter((cr) => cr.status === "CANCELLED").length,
    };

    const outstandingAcks = distributions.length;

    const recentDocs = [...documents]
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .slice(0, 5);

    const upcomingAudits = [...audits]
      .filter((a) => isWithinDays(a.planned_start, 30))
      .sort((a, b) => {
        const da = a.planned_start ? new Date(a.planned_start).getTime() : Infinity;
        const db = b.planned_start ? new Date(b.planned_start).getTime() : Infinity;
        return da - db;
      })
      .slice(0, 5);

    const recentCRs = [...changeRequests]
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .slice(0, 5);

    return {
      docCounts,
      auditCounts,
      crCounts,
      outstandingAcks,
      recentDocs,
      upcomingAudits,
      openCR,
      recentCRs,
    };
  }, [audits, changeRequests, distributions.length, documents]);

  const isQualityDept = department === "quality";

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment={department}>
      <header className="page-header">
        <h1 className="page-header__title">Quality Management System · {amoDisplay}</h1>
        <p className="page-header__subtitle">
          Controlled documents, audit programme, change control, and distribution tracking for {niceDomain("AMO")}.
        </p>
      </header>

      {!isQualityDept && (
        <div className="card card--warning" style={{ marginBottom: 16 }}>
          <p>
            You are viewing the QMS module from the <strong>{department}</strong> dashboard.
            Some actions may be restricted based on role and department.
          </p>
        </div>
      )}

      {state === "loading" && (
        <div className="card card--info">
          <p>Loading QMS overview…</p>
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
        <>
          <section className="page-section">
            <div className="page-section__actions" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                type="button"
                className="primary-chip-btn"
                onClick={load}
              >
                Refresh snapshot
              </button>
            </div>
          </section>

          {/* Widget grid */}
          <section className="page-section">
            <div
              className="page-section__grid"
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                gap: 12,
              }}
            >
              <div className="card">
                <div className="card-header">
                  <h2>Controlled Documents</h2>
                  <p className="text-muted">Status snapshot and latest updates.</p>
                </div>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <span className="badge badge--success">Active: {metrics.docCounts.ACTIVE}</span>
                  <span className="badge badge--neutral">Draft: {metrics.docCounts.DRAFT}</span>
                  <span className="badge badge--warning">Obsolete: {metrics.docCounts.OBSOLETE}</span>
                </div>

                <div style={{ marginTop: 12 }}>
                  <div className="table-primary-text" style={{ marginBottom: 6 }}>
                    Recently updated
                  </div>
                  <div className="table-responsive">
                    <table className="table table-compact">
                      <thead>
                        <tr>
                          <th>Code</th>
                          <th>Title</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metrics.recentDocs.map((d) => (
                          <tr key={d.id}>
                            <td>{d.doc_code}</td>
                            <td>{d.title}</td>
                            <td>{d.status}</td>
                          </tr>
                        ))}
                        {metrics.recentDocs.length === 0 && (
                          <tr>
                            <td colSpan={3} className="text-muted">
                              No documents found.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <h2>Audit Programme</h2>
                  <p className="text-muted">Plan, execute, and track closures.</p>
                </div>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <span className="badge badge--neutral">Planned: {metrics.auditCounts.PLANNED}</span>
                  <span className="badge badge--info">In progress: {metrics.auditCounts.IN_PROGRESS}</span>
                  <span className="badge badge--warning">CAP open: {metrics.auditCounts.CAP_OPEN}</span>
                  <span className="badge badge--success">Closed: {metrics.auditCounts.CLOSED}</span>
                </div>

                <div style={{ marginTop: 12 }}>
                  <div className="table-primary-text" style={{ marginBottom: 6 }}>
                    Upcoming (next 30 days): {metrics.auditCounts.UPCOMING_30D}
                  </div>
                  <div className="table-responsive">
                    <table className="table table-compact">
                      <thead>
                        <tr>
                          <th>Ref</th>
                          <th>Title</th>
                          <th>Start</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metrics.upcomingAudits.map((a) => (
                          <tr key={a.id}>
                            <td>{a.audit_ref}</td>
                            <td>{a.title}</td>
                            <td>{formatDate(a.planned_start)}</td>
                          </tr>
                        ))}
                        {metrics.upcomingAudits.length === 0 && (
                          <tr>
                            <td colSpan={3} className="text-muted">
                              No upcoming audits in the next 30 days.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <h2>Change Control</h2>
                  <p className="text-muted">Requests impacting manuals, processes, and compliance.</p>
                </div>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <span className="badge badge--warning">Open: {metrics.crCounts.OPEN}</span>
                  <span className="badge badge--success">Approved: {metrics.crCounts.APPROVED}</span>
                  <span className="badge badge--danger">Rejected: {metrics.crCounts.REJECTED}</span>
                  <span className="badge badge--neutral">Cancelled: {metrics.crCounts.CANCELLED}</span>
                </div>

                <div style={{ marginTop: 12 }}>
                  <div className="table-primary-text" style={{ marginBottom: 6 }}>
                    Recent requests
                  </div>
                  <div className="table-responsive">
                    <table className="table table-compact">
                      <thead>
                        <tr>
                          <th>Title</th>
                          <th>Status</th>
                          <th>Requested</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metrics.recentCRs.map((cr) => (
                          <tr key={cr.id}>
                            <td>{cr.title}</td>
                            <td>{cr.status}</td>
                            <td>{formatDate(cr.requested_at)}</td>
                          </tr>
                        ))}
                        {metrics.recentCRs.length === 0 && (
                          <tr>
                            <td colSpan={3} className="text-muted">
                              No change requests found.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <h2>Distribution & Read-and-Sign</h2>
                  <p className="text-muted">Outstanding acknowledgements for controlled documents.</p>
                </div>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <span className={metrics.outstandingAcks > 0 ? "badge badge--warning" : "badge badge--success"}>
                    Outstanding acknowledgements: {metrics.outstandingAcks}
                  </span>
                </div>

                <div style={{ marginTop: 12 }}>
                  <p className="text-muted" style={{ margin: 0 }}>
                    This figure is based on distributions marked as "requires acknowledgement" and not yet signed.
                  </p>
                </div>
              </div>
            </div>
          </section>

          <section className="page-section">
            <div className="card">
              <div className="card-header">
                <h2>Finding closure targets</h2>
                <p className="text-muted">
                  Used to drive timely corrective actions (Level 1 / Level 2 / Level 3).
                </p>
              </div>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <span className="badge badge--danger">Level 1: 7 days</span>
                <span className="badge badge--warning">Level 2: 28 days</span>
                <span className="badge badge--info">Level 3: 90 days</span>
              </div>

              <p className="text-muted" style={{ marginTop: 10 }}>
                Next step: we will align the backend finding model to store the level and compute due dates automatically.
              </p>
            </div>
          </section>

          <footer className="page-section">
            <div className="card">
              <p style={{ margin: 0 }}>
                Last refreshed: <strong>{lastRefreshedAt ? lastRefreshedAt.toLocaleString() : ""}</strong>
              </p>
            </div>
          </footer>
        </>
      )}
    </DepartmentLayout>
  );
};

export default QMSHomePage;
