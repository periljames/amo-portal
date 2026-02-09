// src/pages/quality/QMSHomePage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import DashboardCockpit from "../dashboards/DashboardCockpit";
import type { AdminUserRead } from "../services/adminUsers";
import { listAdminUsers } from "../services/adminUsers";
import { getContext } from "../services/auth";
import {
  qmsListCars,
  qmsListAudits,
  qmsListChangeRequests,
  qmsListDistributions,
  qmsListDocuments,
  type CAROut,
  type QMSAuditOut,
  type QMSChangeRequestOut,
  type QMSDistributionOut,
  type QMSDocumentOut,
} from "../services/qms";
import { isUiShellV2Enabled } from "../utils/featureFlags";
import {
  getUserTrainingStatus,
  listTrainingCourses,
  listTrainingEvents,
} from "../services/training";
import type {
  TrainingCourseRead,
  TrainingEventRead,
  TrainingStatusItem,
} from "../types/training";

type LoadState = "idle" | "loading" | "ready" | "error";

type TrainingMatrixItem = {
  user: AdminUserRead;
  items: TrainingStatusItem[];
};

type ScheduledEvent = {
  id: string;
  title: string;
  date: string;
  type: "Audit" | "Training";
  meta?: string;
};

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
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
  const navigate = useNavigate();

  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const uiShellV2 = isUiShellV2Enabled();

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);

  const [documents, setDocuments] = useState<QMSDocumentOut[]>([]);
  const [distributions, setDistributions] = useState<QMSDistributionOut[]>([]);
  const [changeRequests, setChangeRequests] = useState<QMSChangeRequestOut[]>([]);
  const [audits, setAudits] = useState<QMSAuditOut[]>([]);
  const [cars, setCars] = useState<CAROut[]>([]);
  const [trainingEvents, setTrainingEvents] = useState<TrainingEventRead[]>([]);
  const [trainingCourses, setTrainingCourses] = useState<TrainingCourseRead[]>([]);
  const [trainingMatrix, setTrainingMatrix] = useState<TrainingMatrixItem[]>([]);
  const [trainingError, setTrainingError] = useState<string | null>(null);

  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);

  const load = async () => {
    setState("loading");
    setError(null);
    setTrainingError(null);
    try {
      // For now we scope to AMO by default. You can widen later.
      const domain = "AMO";

      const [docs, dists, crs, auds, carsData, coursesData, eventsData] = await Promise.all([
        qmsListDocuments({ domain }),
        qmsListDistributions({ outstanding_only: true }),
        qmsListChangeRequests({ domain }),
        qmsListAudits({ domain }),
        qmsListCars(),
        listTrainingCourses({ include_inactive: false }),
        listTrainingEvents(),
      ]);

      setDocuments(docs);
      setDistributions(dists);
      setChangeRequests(crs);
      setAudits(auds);
      setCars(carsData);
      setTrainingCourses(coursesData);
      setTrainingEvents(eventsData);

      try {
        const users = await listAdminUsers({ limit: 12 });
        const statusResults = await Promise.allSettled(
          users.map((user) => getUserTrainingStatus(user.id))
        );
        const matrix: TrainingMatrixItem[] = users
          .map((user, index) => {
            const res = statusResults[index];
            if (res.status !== "fulfilled") return null;
            return { user, items: res.value };
          })
          .filter(Boolean) as TrainingMatrixItem[];
        setTrainingMatrix(matrix);
      } catch (e: any) {
        setTrainingError(e?.message || "Failed to load training matrix.");
      }

      setLastRefreshedAt(new Date());
      setState("ready");
    } catch (e: any) {
      setState("error");
      setError(e?.message || "Failed to load QMS overview.");
    }
  };

  useEffect(() => {
    if (!uiShellV2) {
      load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uiShellV2]);

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

    const overdueCars = cars.filter((car) => {
      if (!car.due_date) return false;
      if (["CLOSED", "CANCELLED"].includes(car.status)) return false;
      const due = new Date(car.due_date);
      if (Number.isNaN(due.getTime())) return false;
      return due < new Date();
    });

    const openCars = cars.filter(
      (car) => !["CLOSED", "CANCELLED"].includes(car.status)
    );

    const upcomingTrainingEvents = trainingEvents
      .filter((event) => isWithinDays(event.starts_on, 45))
      .sort((a, b) => new Date(a.starts_on).getTime() - new Date(b.starts_on).getTime())
      .slice(0, 5);

    const overdueTraining = trainingMatrix
      .flatMap((entry) =>
        entry.items.map((item) => ({
          user: entry.user,
          item,
        }))
      )
      .filter((entry) => ["OVERDUE", "DUE_SOON"].includes(entry.item.status))
      .sort((a, b) => {
        const da = a.item.days_until_due ?? 9999;
        const db = b.item.days_until_due ?? 9999;
        return da - db;
      })
      .slice(0, 6);

    const events: ScheduledEvent[] = [
      ...audits
        .filter((audit) => audit.planned_start)
        .map((audit) => ({
          id: audit.id,
          title: audit.title,
          date: audit.planned_start as string,
          type: "Audit" as const,
          meta: audit.audit_ref,
        })),
      ...trainingEvents.map((event) => ({
        id: event.id,
        title: event.title,
        date: event.starts_on,
        type: "Training" as const,
        meta: trainingCourses.find((course) => course.id === event.course_id)?.course_id,
      })),
    ]
      .filter((event) => isWithinDays(event.date, 45))
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
      .slice(0, 6);

    const auditClosureRate =
      audits.length > 0
        ? Math.round((auditCounts.CLOSED / audits.length) * 100)
        : 0;

    const compliancePenalty =
      auditCounts.CAP_OPEN * 4 +
      openCR.length * 3 +
      outstandingAcks * 1 +
      overdueCars.length * 6 +
      overdueTraining.filter((entry) => entry.item.status === "OVERDUE").length * 4;

    const complianceScore = Math.max(0, Math.min(100, 100 - compliancePenalty));

    return {
      docCounts,
      auditCounts,
      crCounts,
      outstandingAcks,
      recentDocs,
      upcomingAudits,
      openCR,
      recentCRs,
      overdueCars,
      openCars,
      auditClosureRate,
      upcomingTrainingEvents,
      overdueTraining,
      scheduledEvents: events,
      complianceScore,
    };
  }, [
    audits,
    changeRequests,
    distributions.length,
    documents,
    cars,
    trainingCourses,
    trainingEvents,
    trainingMatrix,
  ]);

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Quality Dashboard"
      subtitle={`Enterprise QMS overview aligned to ${niceDomain("AMO")} standards.`}
      actions={
        uiShellV2 ? null : (
          <button type="button" className="primary-chip-btn" onClick={load}>
            Refresh data
          </button>
        )
      }
    >
      {uiShellV2 ? (
        <DashboardCockpit />
      ) : (
        <>
          {state === "loading" && (
            <div className="card card--info">
              <p>Loading QMS dashboard…</p>
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
            <div
              className="page-section__actions"
              style={{ display: "flex", gap: 8, flexWrap: "wrap" }}
            >
              <button
                type="button"
                className="primary-chip-btn"
                onClick={load}
              >
                Refresh
              </button>

              <button
                type="button"
                className="secondary-chip-btn"
                onClick={() =>
                  navigate(`/maintenance/${amoSlug}/${department}/qms/cars`)
                }
              >
                Open CAR register
              </button>

              <button
                type="button"
                className="secondary-chip-btn"
                onClick={() =>
                  navigate(`/maintenance/${amoSlug}/${department}`)
                }
              >
                Back to dashboard
              </button>
            </div>
          </section>

          <section className="qms-grid qms-grid--attention">
            <div className="qms-card qms-card--wide qms-card--attention">
              <div className="qms-card__header">
                <div>
                  <p className="qms-card__eyebrow">Immediate attention</p>
                  <h2 className="qms-card__title">Quality signals requiring action</h2>
                  <p className="qms-card__subtitle">
                    Red indicators highlight items that are overdue or at risk.
                  </p>
                </div>
              </div>
              <div className="qms-attention-grid">
                <button
                  type="button"
                  className={`qms-attention ${metrics.overdueCars.length > 0 ? "qms-attention--alert qms-attention--pulse" : ""}`}
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/cars`)}
                >
                  <span className="qms-attention__icon">⚠️</span>
                  <span className="qms-attention__label">Overdue CARs</span>
                  <span className="qms-attention__value">{metrics.overdueCars.length}</span>
                  <span className="qms-attention__meta">Escalate overdue corrective actions.</span>
                </button>
                <button
                  type="button"
                  className={`qms-attention ${metrics.overdueTraining.length > 0 ? "qms-attention--alert qms-attention--pulse" : ""}`}
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/training`)}
                >
                  <span className="qms-attention__icon">⚠️</span>
                  <span className="qms-attention__label">Training overdue</span>
                  <span className="qms-attention__value">{metrics.overdueTraining.length}</span>
                  <span className="qms-attention__meta">Staff with overdue or due-soon training.</span>
                </button>
                <button
                  type="button"
                  className={`qms-attention ${metrics.auditCounts.CAP_OPEN > 0 ? "qms-attention--alert qms-attention--pulse" : ""}`}
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/audits`)}
                >
                  <span className="qms-attention__icon">⚠️</span>
                  <span className="qms-attention__label">CAPs open</span>
                  <span className="qms-attention__value">{metrics.auditCounts.CAP_OPEN}</span>
                  <span className="qms-attention__meta">Corrective action plans still open.</span>
                </button>
                <button
                  type="button"
                  className={`qms-attention ${metrics.outstandingAcks > 0 ? "qms-attention--alert qms-attention--pulse" : ""}`}
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/documents`)}
                >
                  <span className="qms-attention__icon">⚠️</span>
                  <span className="qms-attention__label">Outstanding acks</span>
                  <span className="qms-attention__value">{metrics.outstandingAcks}</span>
                  <span className="qms-attention__meta">Read-and-sign still pending.</span>
                </button>
              </div>
            </div>
          </section>

          <section className="qms-grid">
            <div className="qms-card">
              <div className="qms-card__header">
                <div>
                  <h3 className="qms-card__title">Quick actions</h3>
                  <p className="qms-card__subtitle">
                    Jump directly into the areas that need review today.
                  </p>
                </div>
              </div>
              <div className="qms-action-grid">
                <button
                  type="button"
                  className="qms-action"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/audits`)}
                >
                  <span className="qms-action__icon">📋</span>
                  <span className="qms-action__title">Review audit plan</span>
                  <span className="qms-action__meta">Upcoming audits & closures</span>
                </button>
                <button
                  type="button"
                  className="qms-action"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/cars`)}
                >
                  <span className="qms-action__icon">🛠️</span>
                  <span className="qms-action__title">Manage CARs</span>
                  <span className="qms-action__meta">Escalations & ownership</span>
                </button>
                <button
                  type="button"
                  className="qms-action"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/training`)}
                >
                  <span className="qms-action__icon">🎓</span>
                  <span className="qms-action__title">Training matrix</span>
                  <span className="qms-action__meta">Overdue personnel & courses</span>
                </button>
                <button
                  type="button"
                  className="qms-action"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/documents`)}
                >
                  <span className="qms-action__icon">📘</span>
                  <span className="qms-action__title">Document control</span>
                  <span className="qms-action__meta">Manuals & acknowledgements</span>
                </button>
              </div>
            </div>

            <div className="qms-card">
              <div className="qms-card__header">
                <div>
                  <h3 className="qms-card__title">Compliance drivers</h3>
                  <p className="qms-card__subtitle">
                    What is contributing to the current compliance score.
                  </p>
                </div>
              </div>
              <div className="qms-driver">
                <div className="qms-driver__row">
                  <div>
                    <strong>Document currency</strong>
                    <span className="qms-driver__meta">
                      {metrics.docCounts.ACTIVE} active / {documents.length} total
                    </span>
                  </div>
                  <span className="qms-pill qms-pill--info">
                    {documents.length
                      ? Math.round((metrics.docCounts.ACTIVE / documents.length) * 100)
                      : 0}
                    %
                  </span>
                </div>
                <div className="qms-driver__bar">
                  <span
                    style={{
                      width: `${documents.length ? (metrics.docCounts.ACTIVE / documents.length) * 100 : 0}%`,
                    }}
                  />
                </div>

                <div className="qms-driver__row">
                  <div>
                    <strong>Audit closure rate</strong>
                    <span className="qms-driver__meta">
                      {metrics.auditCounts.CLOSED} closed / {audits.length} total
                    </span>
                  </div>
                  <span className="qms-pill">
                    {audits.length
                      ? Math.round((metrics.auditCounts.CLOSED / audits.length) * 100)
                      : 0}
                    %
                  </span>
                </div>
                <div className="qms-driver__bar">
                  <span
                    style={{
                      width: `${audits.length ? (metrics.auditCounts.CLOSED / audits.length) * 100 : 0}%`,
                    }}
                  />
                </div>

                <div className="qms-driver__row">
                  <div>
                    <strong>Training risk</strong>
                    <span className="qms-driver__meta">
                      {metrics.overdueTraining.length} people due/overdue
                    </span>
                  </div>
                  <span
                    className={
                      metrics.overdueTraining.length > 0
                        ? "qms-pill qms-pill--warning"
                        : "qms-pill"
                    }
                  >
                    {metrics.overdueTraining.length}
                  </span>
                </div>
                <div className="qms-driver__bar qms-driver__bar--warning">
                  <span
                    style={{
                      width: `${Math.min(100, metrics.overdueTraining.length * 10)}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          </section>

          <section className="qms-grid qms-grid--summary">
            <div className="qms-card qms-card--hero">
              <div className="qms-card__header">
                <div>
                  <p className="qms-card__eyebrow">Compliance score</p>
                  <h2 className="qms-card__title">Overall Quality Readiness</h2>
                  <p className="qms-card__subtitle">
                    Calculated from audits, CARs, training, and document control signals.
                  </p>
                </div>
                <div className="qms-meter" aria-label="Compliance score">
                  <div
                    className="qms-meter__ring"
                    style={{
                      background: `conic-gradient(var(--qms-accent) ${
                        metrics.complianceScore * 3.6
                      }deg, var(--qms-meter-bg) 0deg)`,
                    }}
                  >
                    <div className="qms-meter__inner">
                      <span className="qms-meter__value">{metrics.complianceScore}%</span>
                      <span className="qms-meter__label">Compliant</span>
                    </div>
                  </div>
                </div>
              </div>
              <div className="qms-kpi-row">
                <button
                  type="button"
                  className="qms-kpi"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/audits`)}
                >
                  <span className="qms-kpi__label">Audit closure rate</span>
                  <span className="qms-kpi__value">{metrics.auditClosureRate}%</span>
                  <span className="qms-kpi__meta">Closed vs total audits</span>
                </button>
                <button
                  type="button"
                  className="qms-kpi"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/documents`)}
                >
                  <span className="qms-kpi__label">Active documents</span>
                  <span className="qms-kpi__value">{metrics.docCounts.ACTIVE}</span>
                  <span className="qms-kpi__meta">{metrics.docCounts.DRAFT} drafts waiting</span>
                </button>
                <button
                  type="button"
                  className="qms-kpi"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/cars`)}
                >
                  <span className="qms-kpi__label">Open CARs</span>
                  <span className="qms-kpi__value">{metrics.openCars.length}</span>
                  <span className="qms-kpi__meta">{metrics.overdueCars.length} overdue</span>
                </button>
                <button
                  type="button"
                  className="qms-kpi"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/training`)}
                >
                  <span className="qms-kpi__label">Training attention</span>
                  <span className="qms-kpi__value">
                    {metrics.overdueTraining.length}
                  </span>
                  <span className="qms-kpi__meta">Overdue or due soon</span>
                </button>
              </div>
            </div>

            <div className="qms-card">
              <div className="qms-card__header">
                <div>
                  <h3 className="qms-card__title">Upcoming audits</h3>
                  <p className="qms-card__subtitle">
                    {metrics.auditCounts.UPCOMING_30D} scheduled in the next 30 days.
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/audits`)}
                >
                  View audit programme
                </button>
              </div>
              <div className="qms-list">
                {metrics.upcomingAudits.map((audit) => (
                  <button
                    type="button"
                    key={audit.id}
                    className="qms-list__item"
                    onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/audits`)}
                  >
                    <div>
                      <strong>{audit.title}</strong>
                      <span className="qms-list__meta">
                        {audit.audit_ref} · Starts {formatDate(audit.planned_start)}
                      </span>
                    </div>
                    <span className="qms-pill qms-pill--info">{audit.status}</span>
                  </button>
                ))}
                {metrics.upcomingAudits.length === 0 && (
                  <p className="text-muted">No audits planned in the next 30 days.</p>
                )}
              </div>
            </div>

            <div className="qms-card">
              <div className="qms-card__header">
                <div>
                  <h3 className="qms-card__title">Scheduled quality events</h3>
                  <p className="qms-card__subtitle">
                    Combined audits, training sessions, and compliance milestones.
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/events`)}
                >
                  View calendar
                </button>
              </div>
              <div className="qms-list">
                {metrics.scheduledEvents.map((event) => (
                  <button
                    type="button"
                    key={`${event.type}-${event.id}`}
                    className="qms-list__item"
                    onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/events`)}
                  >
                    <div>
                      <strong>{event.title}</strong>
                      <span className="qms-list__meta">
                        {event.type} · {formatDate(event.date)}
                        {event.meta ? ` · ${event.meta}` : ""}
                      </span>
                    </div>
                    <span className="qms-pill">{event.type}</span>
                  </button>
                ))}
                {metrics.scheduledEvents.length === 0 && (
                  <p className="text-muted">No events scheduled in the next 45 days.</p>
                )}
              </div>
            </div>
          </section>

          <section className="qms-grid">
            <div className="qms-card">
              <div className="qms-card__header">
                <div>
                  <h3 className="qms-card__title">Change control watchlist</h3>
                  <p className="qms-card__subtitle">
                    {metrics.openCR.length} open changes awaiting review or approval.
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() =>
                    navigate(`/maintenance/${amoSlug}/${department}/qms/change-control`)
                  }
                >
                  Open change control
                </button>
              </div>
              <div className="qms-list">
                {metrics.recentCRs.map((cr) => (
                  <button
                    type="button"
                    key={cr.id}
                    className="qms-list__item"
                    onClick={() =>
                      navigate(`/maintenance/${amoSlug}/${department}/qms/change-control`)
                    }
                  >
                    <div>
                      <strong>{cr.title}</strong>
                      <span className="qms-list__meta">
                        Requested {formatDate(cr.requested_at)}
                      </span>
                    </div>
                    <span className="qms-pill qms-pill--warning">{cr.status}</span>
                  </button>
                ))}
                {metrics.recentCRs.length === 0 && (
                  <p className="text-muted">No change requests logged yet.</p>
                )}
              </div>
            </div>

            <div className="qms-card">
              <div className="qms-card__header">
                <div>
                  <h3 className="qms-card__title">Overdue CARs</h3>
                  <p className="qms-card__subtitle">
                    {metrics.overdueCars.length} CARs past their due dates.
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/cars`)}
                >
                  Open CAR register
                </button>
              </div>
              <div className="qms-list">
                {metrics.overdueCars.slice(0, 5).map((car) => (
                  <button
                    type="button"
                    key={car.id}
                    className="qms-list__item"
                    onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/cars`)}
                  >
                    <div>
                      <strong>{car.title}</strong>
                      <span className="qms-list__meta">
                        Due {formatDate(car.due_date)} · {car.car_number}
                      </span>
                    </div>
                    <span className="qms-pill qms-pill--danger">{car.status}</span>
                  </button>
                ))}
                {metrics.overdueCars.length === 0 && (
                  <p className="text-muted">No overdue CARs right now.</p>
                )}
              </div>
            </div>

            <div className="qms-card">
              <div className="qms-card__header">
                <div>
                  <h3 className="qms-card__title">Document acknowledgements</h3>
                  <p className="qms-card__subtitle">
                    {metrics.outstandingAcks} staff still need to acknowledge latest revisions.
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/documents`)}
                >
                  View document control
                </button>
              </div>
              <div className="qms-split">
                <div>
                  <span className="qms-pill qms-pill--warning">
                    Outstanding: {metrics.outstandingAcks}
                  </span>
                  <p className="text-muted">
                    Track read-and-sign completion for safety-critical manuals.
                  </p>
                </div>
                <div>
                  <span className="qms-pill qms-pill--success">
                    Active: {metrics.docCounts.ACTIVE}
                  </span>
                  <p className="text-muted">Controlled documents currently in use.</p>
                </div>
              </div>
            </div>
          </section>

          <section className="qms-grid">
            <div className="qms-card qms-card--wide">
              <div className="qms-card__header">
                <div>
                  <h3 className="qms-card__title">Overdue personnel</h3>
                  <p className="qms-card__subtitle">
                    Click a row to open the full training record. Click a course to filter the
                    training matrix by course.
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/training`)}
                >
                  Open training matrix
                </button>
              </div>
              {trainingError && (
                <div className="card card--warning">
                  <p>{trainingError}</p>
                </div>
              )}
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Employee</th>
                      <th>Course</th>
                      <th>Status</th>
                      <th>Due date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.overdueTraining.map((entry) => (
                      <tr
                        key={`${entry.user.id}-${entry.item.course_id}`}
                        className="qms-table__row"
                        onClick={() =>
                          navigate(
                            `/maintenance/${amoSlug}/${department}/qms/training/${entry.user.id}`
                          )
                        }
                      >
                        <td>
                          <strong>{entry.user.full_name}</strong>
                          <div className="text-muted">{entry.user.position_title || "Staff"}</div>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="qms-link"
                            onClick={(event) => {
                              event.stopPropagation();
                              navigate(
                                `/maintenance/${amoSlug}/${department}/qms/training?course=${encodeURIComponent(
                                  entry.item.course_id
                                )}`
                              );
                            }}
                          >
                            {entry.item.course_name}
                          </button>
                        </td>
                        <td>
                          <span
                            className={
                              entry.item.status === "OVERDUE"
                                ? "qms-pill qms-pill--danger"
                                : "qms-pill qms-pill--warning"
                            }
                          >
                            {entry.item.status.replace("_", " ")}
                          </span>
                        </td>
                        <td>{formatDate(entry.item.extended_due_date || entry.item.valid_until)}</td>
                      </tr>
                    ))}
                    {metrics.overdueTraining.length === 0 && (
                      <tr>
                        <td colSpan={4} className="text-muted">
                          No overdue or due-soon training at the moment.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="qms-card">
              <div className="qms-card__header">
                <div>
                  <h3 className="qms-card__title">Upcoming training events</h3>
                  <p className="qms-card__subtitle">
                    Scheduled sessions within the next 45 days.
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/events`)}
                >
                  View events
                </button>
              </div>
              <div className="qms-list">
                {metrics.upcomingTrainingEvents.map((event) => (
                  <button
                    type="button"
                    key={event.id}
                    className="qms-list__item"
                    onClick={() => navigate(`/maintenance/${amoSlug}/${department}/qms/events`)}
                  >
                    <div>
                      <strong>{event.title}</strong>
                      <span className="qms-list__meta">
                        Starts {formatDate(event.starts_on)} · {event.location || "TBA"}
                      </span>
                    </div>
                    <span className="qms-pill">{formatDate(event.starts_on)}</span>
                  </button>
                ))}
                {metrics.upcomingTrainingEvents.length === 0 && (
                  <p className="text-muted">No upcoming training events in the next 45 days.</p>
                )}
              </div>
            </div>
          </section>

          <section className="qms-footer">
            <div>
              <strong>Last refreshed</strong>
              <div className="text-muted">
                {lastRefreshedAt ? formatDateTime(lastRefreshedAt.toISOString()) : ""}
              </div>
            </div>
            <div>
              <strong>Signals monitored</strong>
              <div className="text-muted">
                Audits, CARs, training compliance, document control, change requests.
              </div>
            </div>
          </section>
            </>
          )}
        </>
      )}
    </QMSLayout>
  );
};

export default QMSHomePage;
