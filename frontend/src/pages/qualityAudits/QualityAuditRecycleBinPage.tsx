import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import {
  AlertTriangle,
  ArchiveRestore,
  CalendarClock,
  FileClock,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";
import Button from "../../components/UI/Button";
import InlineError from "../../components/shared/InlineError";
import { useToast } from "../../components/feedback/ToastProvider";
import { hasQmsRolePermission } from "../../app/routeGuards";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import {
  qmsGetAuditDeletionImpact,
  qmsListAllAudits,
  qmsListAuditSchedules,
  qmsPurgeAudit,
  qmsPurgeAuditSchedule,
  qmsRestoreAudit,
  qmsRestoreAuditSchedule,
  type AuditDeletionImpact,
  type QMSAuditOut,
  type QMSAuditScheduleOut,
} from "../../services/qms";
import "./quality-audit-recycle-bin.css";

type RecoverableRow = {
  id: string;
  recordType: "audit" | "schedule";
  reference: string;
  title: string;
  state: string;
  detail: string;
  deletedAt: string;
  purgeAt: string;
  daysRemaining: number;
  reason: string;
  source: QMSAuditOut | QMSAuditScheduleOut;
};

type PendingAction = {
  kind: "restore" | "purge";
  row: RecoverableRow;
};

function formatDateTime(value?: string | null): string {
  if (!value) return "Unavailable";
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

function formatDate(value?: string | null): string {
  if (!value) return "Not scheduled";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/^./, (letter) => letter.toUpperCase());
}

function errorMessage(error: unknown): string | null {
  if (!error) return null;
  return error instanceof Error ? error.message : String(error);
}

function RecordCell({ data }: ICellRendererParams<RecoverableRow>) {
  if (!data) return null;
  return (
    <div className="qa-bin-record">
      <strong>{data.reference}</strong>
      <span>{data.title}</span>
    </div>
  );
}

function RetentionCell({ data }: ICellRendererParams<RecoverableRow>) {
  if (!data) return null;
  const urgent = data.daysRemaining <= 7;
  return (
    <div className={`qa-bin-retention${urgent ? " is-urgent" : ""}`}>
      <strong>{data.daysRemaining === 0 ? "Due now" : `${data.daysRemaining} day${data.daysRemaining === 1 ? "" : "s"}`}</strong>
      <span>{formatDateTime(data.purgeAt)}</span>
    </div>
  );
}

const QualityAuditRecycleBinPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<"all" | "audit" | "schedule">("all");
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [purgeImpact, setPurgeImpact] = useState<AuditDeletionImpact | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const auditsQuery = useQuery({
    queryKey: ["qms-audit-recycle-bin", "audits"],
    queryFn: () => qmsListAllAudits({ domain: "AMO", deleted_only: true, limit: 500 }),
    staleTime: 15_000,
  });

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-recycle-bin", "schedules"],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", deleted_only: true, limit: 500 }),
    staleTime: 15_000,
  });

  const deletedAudits = useMemo(() => auditsQuery.data ?? [], [auditsQuery.data]);
  const deletedSchedules = useMemo(() => schedulesQuery.data ?? [], [schedulesQuery.data]);
  const loading = auditsQuery.isLoading || schedulesQuery.isLoading;
  const firstError = errorMessage(auditsQuery.error) || errorMessage(schedulesQuery.error);

  const rows = useMemo<RecoverableRow[]>(() => {
    const auditRows = deletedAudits.map((audit) => ({
      id: audit.id,
      recordType: "audit" as const,
      reference: audit.audit_ref,
      title: audit.title,
      state: humanize(audit.status),
      detail: `${formatDate(audit.planned_start)} – ${formatDate(audit.planned_end)}`,
      deletedAt: audit.deleted_at ?? "",
      purgeAt: audit.purge_at ?? "",
      daysRemaining: audit.days_remaining ?? 0,
      reason: audit.delete_reason?.trim() || "No reason provided",
      source: audit,
    }));
    const scheduleRows = deletedSchedules.map((schedule) => ({
      id: schedule.id,
      recordType: "schedule" as const,
      reference: "Audit schedule",
      title: schedule.title,
      state: humanize(schedule.frequency),
      detail: `Next due ${formatDate(schedule.next_due_date)}`,
      deletedAt: schedule.deleted_at ?? "",
      purgeAt: schedule.purge_at ?? "",
      daysRemaining: schedule.days_remaining ?? 0,
      reason: schedule.delete_reason?.trim() || "No reason provided",
      source: schedule,
    }));
    return [...auditRows, ...scheduleRows].sort((left, right) => right.deletedAt.localeCompare(left.deletedAt));
  }, [deletedAudits, deletedSchedules]);

  const filteredRows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (typeFilter !== "all" && row.recordType !== typeFilter) return false;
      if (!needle) return true;
      return [row.reference, row.title, row.state, row.detail, row.reason]
        .some((value) => value.toLowerCase().includes(needle));
    });
  }, [rows, search, typeFilter]);

  const invalidateAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-recycle-bin"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-dashboard"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-dashboard-audits"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-dashboard-schedules"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audits-workspace"] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-programme"] }),
    ]);
  };

  const impactMutation = useMutation({
    mutationFn: (auditId: string) => qmsGetAuditDeletionImpact(auditId),
    onSuccess: (impact) => setPurgeImpact(impact),
    onError: (error: Error) => setDialogError(error.message || "Associated records could not be inspected."),
  });

  const restoreMutation = useMutation({
    mutationFn: async (row: RecoverableRow) => {
      if (row.recordType === "audit") await qmsRestoreAudit(row.id);
      else await qmsRestoreAuditSchedule(row.id);
      return row;
    },
    onSuccess: async (row) => {
      setPendingAction(null);
      await invalidateAll();
      pushToast({
        title: `${row.recordType === "audit" ? "Audit" : "Schedule"} restored`,
        message: `${row.title} is back in its previous workflow state.`,
        variant: "success",
      });
    },
    onError: (error: Error) => setDialogError(error.message || "The record could not be restored."),
  });

  const purgeMutation = useMutation({
    mutationFn: async (row: RecoverableRow) => {
      if (row.recordType === "audit") await qmsPurgeAudit(row.id);
      else await qmsPurgeAuditSchedule(row.id);
      return row;
    },
    onSuccess: async (row) => {
      setPendingAction(null);
      setPurgeImpact(null);
      await invalidateAll();
      pushToast({
        title: "Permanently deleted",
        message: `${row.title} has been purged and cannot be restored.`,
        variant: "success",
      });
    },
    onError: (error: Error) => setDialogError(error.message || "The record could not be permanently deleted."),
  });

  const closeDialog = () => {
    if (restoreMutation.isPending || purgeMutation.isPending) return;
    setPendingAction(null);
    setPurgeImpact(null);
    setDialogError(null);
  };

  const openAction = (kind: PendingAction["kind"], row: RecoverableRow) => {
    setPendingAction({ kind, row });
    setPurgeImpact(null);
    setDialogError(null);
    if (kind === "purge" && row.recordType === "audit") impactMutation.mutate(row.id);
  };

  const columnDefs: ColDef<RecoverableRow>[] = [
    { headerName: "Record", field: "title", minWidth: 260, flex: 1.5, cellRenderer: RecordCell },
    {
      headerName: "Type",
      field: "recordType",
      width: 105,
      cellRenderer: ({ value }: ICellRendererParams<RecoverableRow>) => (
        <span className="qa-bin-type">{value === "audit" ? "Audit" : "Schedule"}</span>
      ),
    },
    { headerName: "Previous state", field: "state", minWidth: 135, flex: 0.75 },
    { headerName: "Schedule", field: "detail", minWidth: 190, flex: 1 },
    {
      headerName: "Deleted",
      field: "deletedAt",
      minWidth: 175,
      flex: 0.9,
      valueFormatter: ({ value }) => formatDateTime(value),
      sort: "desc",
    },
    { headerName: "Auto-delete", field: "purgeAt", minWidth: 175, flex: 0.9, cellRenderer: RetentionCell },
    { headerName: "Reason", field: "reason", minWidth: 170, flex: 1, tooltipField: "reason" },
    {
      headerName: "Actions",
      field: "id",
      width: 116,
      pinned: "right",
      sortable: false,
      filter: false,
      cellRenderer: ({ data }: ICellRendererParams<RecoverableRow>) => data ? (
        <div className="qa-bin-actions">
          <button type="button" title="Restore" aria-label={`Restore ${data.title}`} disabled={!canManage} onClick={() => openAction("restore", data)}>
            <ArchiveRestore size={15} />
          </button>
          <button type="button" className="is-danger" title="Delete forever" aria-label={`Delete ${data.title} forever`} disabled={!canManage} onClick={() => openAction("purge", data)}>
            <Trash2 size={15} />
          </button>
        </div>
      ) : null,
    },
  ];

  const expiringSoon = rows.filter((row) => row.daysRemaining <= 7).length;
  const actionPending = restoreMutation.isPending || purgeMutation.isPending;
  const waitingForImpact = pendingAction?.kind === "purge"
    && pendingAction.row.recordType === "audit"
    && impactMutation.isPending;
  const canConfirm = Boolean(pendingAction) && !actionPending && !waitingForImpact
    && !(pendingAction?.kind === "purge" && pendingAction.row.recordType === "audit" && !purgeImpact);

  return (
    <QualityAuditsSectionLayout
      title="Recycle bin"
      subtitle="Restore audits and schedules with their prior workflow state, or permanently delete them. Items are retained for 30 days."
      toolbar={(
        <Button size="sm" variant="secondary" onClick={() => void Promise.all([auditsQuery.refetch(), schedulesQuery.refetch()])} loading={auditsQuery.isFetching || schedulesQuery.isFetching}>
          <RefreshCw size={14} /> Refresh
        </Button>
      )}
    >
      <div className="qa-bin-page">
        {firstError ? <InlineError message={firstError} /> : null}

        <section className="qa-bin-summary" aria-label="Recycle bin summary">
          <article><FileClock size={17} /><div><strong>{loading ? "—" : rows.length}</strong><span>Recoverable</span></div></article>
          <article><ArchiveRestore size={17} /><div><strong>{loading ? "—" : deletedAudits.length}</strong><span>Audits</span></div></article>
          <article><CalendarClock size={17} /><div><strong>{loading ? "—" : deletedSchedules.length}</strong><span>Schedules</span></div></article>
          <article className={expiringSoon ? "is-warning" : ""}><AlertTriangle size={17} /><div><strong>{loading ? "—" : expiringSoon}</strong><span>Delete within 7 days</span></div></article>
        </section>

        <section className="qa-bin-register">
          <header>
            <div>
              <h2>Deleted records</h2>
              <p>Restoring clears only the deletion marker; the saved lifecycle and all linked records remain unchanged.</p>
            </div>
            <div className="qa-bin-controls">
              <div className="qa-bin-segments" role="group" aria-label="Filter record type">
                {(["all", "audit", "schedule"] as const).map((value) => (
                  <button key={value} type="button" className={typeFilter === value ? "is-active" : ""} onClick={() => setTypeFilter(value)}>
                    {value === "all" ? "All" : value === "audit" ? "Audits" : "Schedules"}
                  </button>
                ))}
              </div>
              <label className="qa-bin-search">
                <Search size={15} aria-hidden />
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search deleted records" aria-label="Search deleted records" />
              </label>
            </div>
          </header>

          <div className="ag-theme-alpine qa-bin-grid">
            <AgGridReact<RecoverableRow>
              rowData={filteredRows}
              columnDefs={columnDefs}
              defaultColDef={{ sortable: true, resizable: true, suppressHeaderMenuButton: true }}
              getRowId={({ data }) => `${data.recordType}:${data.id}`}
              pagination
              paginationPageSize={25}
              paginationPageSizeSelector={[25, 50, 100]}
              rowHeight={54}
              headerHeight={38}
              overlayLoadingTemplate="<span>Loading deleted records…</span>"
              overlayNoRowsTemplate="<span>The recycle bin is empty.</span>"
              loading={loading}
            />
          </div>
        </section>
      </div>

      {pendingAction ? (
        <div className="qa-bin-dialog" role="presentation" onMouseDown={closeDialog}>
          <section role="alertdialog" aria-modal="true" aria-labelledby="qa-bin-dialog-title" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div className={pendingAction.kind === "purge" ? "is-danger" : ""}>
                {pendingAction.kind === "restore" ? <ArchiveRestore size={20} /> : <AlertTriangle size={20} />}
                <h2 id="qa-bin-dialog-title">{pendingAction.kind === "restore" ? "Restore this record?" : "Delete forever?"}</h2>
              </div>
              <button type="button" aria-label="Close" disabled={actionPending} onClick={closeDialog}><X size={18} /></button>
            </header>
            <p><strong>{pendingAction.row.reference} · {pendingAction.row.title}</strong></p>

            {pendingAction.kind === "restore" ? (
              <div className="qa-bin-dialog__info">
                The record returns to its previous {pendingAction.row.recordType === "audit" ? "audit lifecycle" : "planning state"}. Linked workflow data is already preserved and becomes available again immediately.
              </div>
            ) : (
              <>
                {waitingForImpact ? <div className="qa-bin-dialog__info">Inspecting all records that will be removed…</div> : null}
                {purgeImpact ? (
                  <div className="qa-bin-dialog__impact">
                    <ul>
                      {purgeImpact.groups.map((group) => <li key={group.key}><span>{group.label}</span><strong>{group.count}</strong></li>)}
                      <li><span>Managed audit files</span><strong>{purgeImpact.managed_file_count}</strong></li>
                    </ul>
                    <small>{purgeImpact.database_record_count} database records including the audit. Shared controlled DMS sources are preserved.</small>
                  </div>
                ) : pendingAction.row.recordType === "schedule" ? (
                  <div className="qa-bin-dialog__info">The recurring schedule and its schedule-owned planner links will be removed. Audits already created from it are preserved.</div>
                ) : null}
                <div className="qa-bin-dialog__warning">This action cannot be undone.</div>
              </>
            )}
            {dialogError ? <p className="qa-bin-dialog__error" role="alert">{dialogError}</p> : null}
            <footer>
              <button type="button" disabled={actionPending} onClick={closeDialog}>Cancel</button>
              <button
                type="button"
                className={pendingAction.kind === "purge" ? "is-danger" : "is-primary"}
                disabled={!canConfirm}
                onClick={() => pendingAction.kind === "restore" ? restoreMutation.mutate(pendingAction.row) : purgeMutation.mutate(pendingAction.row)}
              >
                {pendingAction.kind === "restore" ? <ArchiveRestore size={15} /> : <Trash2 size={15} />}
                {actionPending ? "Working…" : pendingAction.kind === "restore" ? "Restore" : "Delete forever"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditRecycleBinPage;
