import React, { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, FileWarning, RefreshCw, Trash2 } from "lucide-react";
import Button from "../../components/UI/Button";
import InlineError from "../../components/shared/InlineError";
import { useToast } from "../../components/feedback/ToastProvider";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import {
  qmsListAudits,
  qmsListAuditSchedules,
  qmsPurgeAudit,
  qmsPurgeAuditSchedule,
  qmsRestoreAudit,
  qmsRestoreAuditSchedule,
  type QMSAuditOut,
  type QMSAuditScheduleOut,
} from "../../services/qms";

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function errorMessage(error: unknown): string | null {
  if (!error) return null;
  return error instanceof Error ? error.message : String(error);
}

const QualityAuditRecycleBinPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();

  const auditsQuery = useQuery({
    queryKey: ["qms-audit-recycle-bin", "audits"],
    queryFn: () => qmsListAudits({ domain: "AMO", deleted_only: true, limit: 500 }),
    staleTime: 30_000,
  });

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-recycle-bin", "schedules"],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", deleted_only: true, limit: 500 }),
    staleTime: 30_000,
  });

  const deletedAudits = auditsQuery.data ?? [];
  const deletedSchedules = schedulesQuery.data ?? [];
  const loading = auditsQuery.isLoading || schedulesQuery.isLoading;
  const firstError = errorMessage(auditsQuery.error) || errorMessage(schedulesQuery.error);

  const refresh = async () => {
    await Promise.all([auditsQuery.refetch(), schedulesQuery.refetch()]);
  };

  const invalidateAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-recycle-bin"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-dashboard"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-dashboard-audits"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-dashboard-schedules"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules"] }),
    ]);
  };

  const restoreAudit = useMutation({
    mutationFn: (audit: QMSAuditOut) => qmsRestoreAudit(audit.id).then(() => audit),
    onSuccess: async (audit) => {
      await invalidateAll();
      pushToast({ title: "Audit restored", message: `${audit.audit_ref} is back in the active audit register.`, variant: "success" });
    },
    onError: (error: Error) => pushToast({ title: "Restore failed", message: error.message, variant: "error" }),
  });

  const purgeAudit = useMutation({
    mutationFn: (audit: QMSAuditOut) => qmsPurgeAudit(audit.id).then(() => audit),
    onSuccess: async (audit) => {
      await invalidateAll();
      pushToast({ title: "Audit permanently deleted", message: `${audit.audit_ref} has been removed permanently.`, variant: "success" });
    },
    onError: (error: Error) => pushToast({ title: "Permanent delete failed", message: error.message, variant: "error" }),
  });

  const restoreSchedule = useMutation({
    mutationFn: (schedule: QMSAuditScheduleOut) => qmsRestoreAuditSchedule(schedule.id).then(() => schedule),
    onSuccess: async (schedule) => {
      await invalidateAll();
      pushToast({ title: "Schedule restored", message: `${schedule.title} is active again.`, variant: "success" });
    },
    onError: (error: Error) => pushToast({ title: "Restore failed", message: error.message, variant: "error" }),
  });

  const purgeSchedule = useMutation({
    mutationFn: (schedule: QMSAuditScheduleOut) => qmsPurgeAuditSchedule(schedule.id).then(() => schedule),
    onSuccess: async (schedule) => {
      await invalidateAll();
      pushToast({ title: "Schedule permanently deleted", message: `${schedule.title} has been removed permanently.`, variant: "success" });
    },
    onError: (error: Error) => pushToast({ title: "Permanent delete failed", message: error.message, variant: "error" }),
  });

  const totals = useMemo(
    () => [
      { label: "Deleted audits", value: deletedAudits.length },
      { label: "Deleted schedules", value: deletedSchedules.length },
      { label: "Total recoverable", value: deletedAudits.length + deletedSchedules.length },
    ],
    [deletedAudits.length, deletedSchedules.length]
  );

  return (
    <QualityAuditsSectionLayout
      title="Audit recycle bin"
      subtitle="Recover soft-deleted audits and schedules, or permanently remove records already reviewed for deletion."
      toolbar={
        <Button size="sm" variant="secondary" onClick={() => void refresh()} loading={auditsQuery.isFetching || schedulesQuery.isFetching}>
          <RefreshCw size={14} /> Refresh
        </Button>
      }
    >
      <div className="audit-workspace">
        {firstError ? <InlineError message={firstError} /> : null}

        <section className="audit-stats-grid">
          {totals.map((item) => (
            <div key={item.label} className="audit-stat-card">
              <div className="audit-stat-card__label"><FileWarning size={15} /> {item.label}</div>
              <div className="audit-stat-card__value">{loading ? "—" : item.value}</div>
            </div>
          ))}
        </section>

        <section className="audit-panel">
          <div className="audit-panel__header">
            <div>
              <h2 className="audit-panel__title">Deleted audit records</h2>
              <p className="audit-panel__subtitle">Restore records to the active workflow or permanently delete them after final review.</p>
            </div>
          </div>
          <div className="table-wrapper">
            <table className="table table--wrap">
              <thead>
                <tr>
                  <th>Audit</th>
                  <th>Status</th>
                  <th>Window</th>
                  <th>Deleted</th>
                  <th>Reason</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {deletedAudits.length === 0 ? (
                  <tr><td colSpan={6}>No deleted audit records.</td></tr>
                ) : deletedAudits.map((audit) => (
                  <tr key={audit.id}>
                    <td><strong>{audit.audit_ref}</strong><div className="text-muted">{audit.title}</div></td>
                    <td><span className="qms-pill">{audit.status}</span></td>
                    <td>{formatDate(audit.planned_start)} → {formatDate(audit.planned_end)}</td>
                    <td>{formatDateTime(audit.deleted_at)}</td>
                    <td>{audit.delete_reason || "—"}</td>
                    <td>
                      <div className="audit-chip-list">
                        <button type="button" className="secondary-chip-btn" onClick={() => restoreAudit.mutate(audit)} disabled={restoreAudit.isPending}>
                          <ArchiveRestore size={14} /> Restore
                        </button>
                        <button
                          type="button"
                          className="secondary-chip-btn secondary-chip-btn--danger"
                          onClick={() => {
                            if (window.confirm(`Permanently delete audit ${audit.audit_ref}? This cannot be undone.`)) purgeAudit.mutate(audit);
                          }}
                          disabled={purgeAudit.isPending}
                        >
                          <Trash2 size={14} /> Delete forever
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="audit-panel">
          <div className="audit-panel__header">
            <div>
              <h2 className="audit-panel__title">Deleted schedules</h2>
              <p className="audit-panel__subtitle">Schedules return to active planning when restored.</p>
            </div>
          </div>
          <div className="table-wrapper">
            <table className="table table--wrap">
              <thead>
                <tr>
                  <th>Schedule</th>
                  <th>Frequency</th>
                  <th>Next due</th>
                  <th>Deleted</th>
                  <th>Reason</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {deletedSchedules.length === 0 ? (
                  <tr><td colSpan={6}>No deleted schedules.</td></tr>
                ) : deletedSchedules.map((schedule) => (
                  <tr key={schedule.id}>
                    <td><strong>{schedule.title}</strong><div className="text-muted">{schedule.auditee || "Auditee not set"}</div></td>
                    <td><span className="qms-pill">{schedule.frequency}</span></td>
                    <td>{formatDate(schedule.next_due_date)}</td>
                    <td>{formatDateTime(schedule.deleted_at)}</td>
                    <td>{schedule.delete_reason || "—"}</td>
                    <td>
                      <div className="audit-chip-list">
                        <button type="button" className="secondary-chip-btn" onClick={() => restoreSchedule.mutate(schedule)} disabled={restoreSchedule.isPending}>
                          <ArchiveRestore size={14} /> Restore
                        </button>
                        <button
                          type="button"
                          className="secondary-chip-btn secondary-chip-btn--danger"
                          onClick={() => {
                            if (window.confirm(`Permanently delete schedule ${schedule.title}? This cannot be undone.`)) purgeSchedule.mutate(schedule);
                          }}
                          disabled={purgeSchedule.isPending}
                        >
                          <Trash2 size={14} /> Delete forever
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditRecycleBinPage;
