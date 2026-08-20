import React, { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import Button from "../../components/UI/Button";
import InlineError from "../../components/shared/InlineError";
import { getContext } from "../../services/auth";
import { qmsListAudits, qmsListCars } from "../../services/qms";
import { listPlannerAuditSchedules } from "../../services/qmsPlannerSchedules";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import "./quality-audit-dashboard.css";

const ACTIVE_CAR_STATUSES = new Set(["DRAFT", "OPEN", "IN_PROGRESS", "PENDING_VERIFICATION", "ESCALATED"]);

function todayDateOnly(): string {
  return new Date().toISOString().slice(0, 10);
}

function formatDate(value?: string | null): string {
  if (!value) return "Not set";
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

function formatStatus(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (char) => char.toUpperCase());
}

function queryError(error: unknown): string | null {
  if (!error) return null;
  return error instanceof Error ? error.message : String(error);
}

const QualityAuditAssuranceDashboardPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const today = todayDateOnly();

  const schedulesQuery = useQuery({
    queryKey: ["qms-authoritative-planner-schedules", amoCode, "active"],
    queryFn: ({ signal }) => listPlannerAuditSchedules(amoCode, { active: true, limit: 500 }, signal),
    staleTime: 30_000,
  });
  const auditsQuery = useQuery({
    queryKey: ["qms-audit-dashboard-audits", amoCode],
    queryFn: () => qmsListAudits({ domain: "AMO", limit: 500 }, { silent: true }),
    staleTime: 30_000,
  });
  const carsQuery = useQuery({
    queryKey: ["qms-audit-dashboard-cars", amoCode],
    queryFn: () => qmsListCars({ program: "QUALITY", limit: 500 }, { silent: true }),
    staleTime: 30_000,
  });

  const schedules = schedulesQuery.data ?? [];
  const audits = auditsQuery.data ?? [];
  const cars = carsQuery.data ?? [];
  const activeAudits = useMemo(() => audits.filter((audit) => audit.status !== "CLOSED"), [audits]);
  const openCars = useMemo(() => cars.filter((car) => ACTIVE_CAR_STATUSES.has(car.status)), [cars]);
  const overdueSchedules = useMemo(() => schedules.filter((schedule) => schedule.next_due_date < today), [schedules, today]);
  const unassignedSchedules = useMemo(() => schedules.filter((schedule) => !schedule.lead_auditor_user_id), [schedules]);
  const upcomingSchedules = useMemo(
    () => schedules.filter((schedule) => schedule.next_due_date >= today).sort((a, b) => a.next_due_date.localeCompare(b.next_due_date)).slice(0, 8),
    [schedules, today],
  );

  const firstError = queryError(schedulesQuery.error) || queryError(auditsQuery.error) || queryError(carsQuery.error);
  const refreshing = schedulesQuery.isFetching || auditsQuery.isFetching || carsQuery.isFetching;
  const refresh = async () => {
    await Promise.all([schedulesQuery.refetch(), auditsQuery.refetch(), carsQuery.refetch()]);
  };

  return (
    <QualityAuditsSectionLayout
      title="Audit assurance"
      subtitle="Current audit programme commitments and live assurance work from the authoritative Quality Planner."
      toolbar={
        <div className="audit-chip-list">
          <Link className="btn btn--sm" to={`/maintenance/${encodeURIComponent(amoCode)}/quality/calendar/week`}>
            <CalendarClock size={14} /> Open planner
          </Link>
          <Button size="sm" variant="secondary" onClick={() => void refresh()} loading={refreshing}>
            <RefreshCw size={14} /> Refresh
          </Button>
        </div>
      }
    >
      <div className="audit-workspace">
        {firstError ? <InlineError message={firstError} onAction={() => void refresh()} /> : null}

        <section className="audit-stats-grid" aria-label="Audit assurance summary">
          <article className="audit-stat-card">
            <div className="audit-stat-card__label"><CalendarClock size={15} /> Active schedules</div>
            <div className="audit-stat-card__value">{schedules.length}</div>
            <div className="audit-stat-card__helper">Governed planner schedule templates</div>
          </article>
          <article className="audit-stat-card">
            <div className="audit-stat-card__label"><AlertTriangle size={15} /> Overdue schedules</div>
            <div className="audit-stat-card__value">{overdueSchedules.length}</div>
            <div className="audit-stat-card__helper">Dates earlier than {formatDate(today)}</div>
          </article>
          <article className="audit-stat-card">
            <div className="audit-stat-card__label"><ClipboardList size={15} /> Active audit occurrences</div>
            <div className="audit-stat-card__value">{activeAudits.length}</div>
            <div className="audit-stat-card__helper">Materialized audits not yet closed</div>
          </article>
          <article className="audit-stat-card">
            <div className="audit-stat-card__label"><ShieldCheck size={15} /> Open CAR/CAPA</div>
            <div className="audit-stat-card__value">{openCars.length}</div>
            <div className="audit-stat-card__helper">Quality corrective-action workload</div>
          </article>
        </section>

        <section className="audit-panel">
          <div className="audit-panel__header">
            <div>
              <h2 className="audit-panel__title">Upcoming governed schedules</h2>
              <p className="audit-panel__subtitle">These records come from `/integrations/calendar/audit-schedules`; no legacy schedule API is queried.</p>
            </div>
          </div>
          <div className="table-wrapper">
            <table className="table table--wrap">
              <thead>
                <tr>
                  <th>Schedule</th>
                  <th>Kind</th>
                  <th>Frequency</th>
                  <th>Next due</th>
                  <th>Lead</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {upcomingSchedules.length ? upcomingSchedules.map((schedule) => (
                  <tr key={schedule.id}>
                    <td>
                      <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/calendar/week?date=${encodeURIComponent(schedule.next_due_date)}`}>
                        <strong>{schedule.title}</strong>
                      </Link>
                      <div className="text-muted">{schedule.audit_scope_code || "Governed default scope"}</div>
                    </td>
                    <td>{formatStatus(schedule.kind)}</td>
                    <td>{formatStatus(schedule.frequency)}</td>
                    <td>{formatDate(schedule.next_due_date)}</td>
                    <td>{schedule.lead_auditor_user_id || "Unassigned"}</td>
                    <td><span className="qms-pill">{formatStatus(schedule.lifecycle_status)}</span></td>
                  </tr>
                )) : (
                  <tr><td colSpan={6}>No upcoming audit schedules.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="audit-panel">
          <div className="audit-panel__header">
            <div>
              <h2 className="audit-panel__title">Attention required</h2>
              <p className="audit-panel__subtitle">Planner conditions that should be resolved before occurrence materialization.</p>
            </div>
          </div>
          <div className="audit-action-grid">
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/calendar/week?date=${encodeURIComponent(today)}`} className="audit-action-card">
              <AlertTriangle size={18} /><strong>{overdueSchedules.length} overdue schedule{overdueSchedules.length === 1 ? "" : "s"}</strong><span>Review and reschedule with an attributable reason.</span>
            </Link>
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/calendar/week`} className="audit-action-card">
              <ShieldCheck size={18} /><strong>{unassignedSchedules.length} unassigned schedule{unassignedSchedules.length === 1 ? "" : "s"}</strong><span>Assign eligible auditors through governed Planner controls.</span>
            </Link>
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits/register`} className="audit-action-card">
              <CheckCircle2 size={18} /><strong>{activeAudits.length} active occurrence{activeAudits.length === 1 ? "" : "s"}</strong><span>Continue setup, preparation, fieldwork and closeout.</span>
            </Link>
          </div>
        </section>

        <small className="text-muted">Department context: {department}. Schedule identity, version and lifecycle are owned by the Quality Operations Planner.</small>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditAssuranceDashboardPage;
