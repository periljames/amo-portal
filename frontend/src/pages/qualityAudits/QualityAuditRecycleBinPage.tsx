import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, FileWarning, RefreshCw, Trash2 } from "lucide-react";

import Button from "../../components/UI/Button";
import InlineError from "../../components/shared/InlineError";
import { useToast } from "../../components/feedback/ToastProvider";
import {
  qmsListAudits,
  qmsPurgeAudit,
  qmsRestoreAudit,
  type QMSAuditOut,
} from "../../services/qms";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
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

  const deletedAudits = auditsQuery.data ?? [];
  const firstError = errorMessage(auditsQuery.error);

  const invalidateAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-recycle-bin"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-dashboard"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-dashboard-audits"] }),
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

  return (
    <QualityAuditsSectionLayout
      title="Audit recycle bin"
      subtitle="Recover or permanently remove deleted audit occurrences. Schedule templates are suspended/resumed in the Planner and are not a parallel recycle-bin lifecycle."
      toolbar={
        <Button size="sm" variant="secondary" onClick={() => void auditsQuery.refetch()} loading={auditsQuery.isFetching}>
          <RefreshCw size={14} /> Refresh
        </Button>
      }
    >
      <div className="audit-workspace">
        {firstError ? <InlineError message={firstError} onAction={() => void auditsQuery.refetch()} /> : null}

        <section className="audit-stats-grid">
          <div className="audit-stat-card">
            <div className="audit-stat-card__label"><FileWarning size={15} /> Deleted audits</div>
            <div className="audit-stat-card__value">{auditsQuery.isLoading ? "—" : deletedAudits.length}</div>
            <div className="audit-stat-card__helper">Recoverable audit occurrences only</div>
          </div>
        </section>

        <section className="audit-panel">
          <div className="audit-panel__header">
            <div>
              <h2 className="audit-panel__title">Deleted audit records</h2>
              <p className="audit-panel__subtitle">Restore records to the governed audit workflow or permanently remove them after final review.</p>
            </div>
          </div>
          <div className="table-wrapper">
            <table className="table table--wrap">
              <thead>
                <tr>
                  <th>Audit</th>
                  <th>Status</th>
                  <th>Deleted</th>
                  <th>Reason</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {deletedAudits.length === 0 ? (
                  <tr><td colSpan={5}>No deleted audit records.</td></tr>
                ) : deletedAudits.map((audit) => (
                  <tr key={audit.id}>
                    <td><strong>{audit.audit_ref}</strong><div className="text-muted">{audit.title}</div></td>
                    <td><span className="qms-pill">{audit.status}</span></td>
                    <td>{formatDate(audit.deleted_at)}</td>
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
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditRecycleBinPage;
