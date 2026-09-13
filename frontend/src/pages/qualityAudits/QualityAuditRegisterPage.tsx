import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { ColDef, ICellRendererParams, RowDoubleClickedEvent } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import {
  BarChart3,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  ClipboardList,
  ExternalLink,
  RefreshCw,
  Search,
  ShieldAlert,
} from "lucide-react";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";

import { hasQmsRolePermission } from "../../app/routeGuards";
import { getContext } from "../../services/auth";
import { qmsGetAuditRegisterPage } from "../../services/qmsRegisters";
import type { CAROut, QMSAuditOut, QMSFindingOut } from "../../services/qms";
import { auditNavigationHref } from "./auditNavigation";
import { qmsModulePath, qmsRecordPath } from "../qms/routes/qmsRouteRegistry";
import { parseQmsRegisterFilters, withQmsQuery, buildPreservedQmsQuery } from "../qms/routes/qmsQueryState";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import {
  FINDING_LIFECYCLE_OPTIONS,
  findingLifecycleLabel,
  findingLifecycleView,
  findingNextAction,
  primaryLinkedCar,
  toRegisterWorkflowStage,
  type FindingLifecycleView,
} from "./findingLifecycle";
import "./quality-audits-list-workspace.css";

type RegisterPageSize = 25 | 50 | 100;

type RegisterRow = {
  id: string;
  audit: QMSAuditOut;
  finding: QMSFindingOut;
  linkedCars: CAROut[];
  lifecycle: FindingLifecycleView;
  primaryCar: CAROut | null;
};

function humanize(value: unknown): string {
  return String(value || "").replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isObservation(finding: QMSFindingOut): boolean {
  return String(finding.finding_type || "").toUpperCase() === "OBSERVATION"
    || String(finding.level || "").toUpperCase().includes("LEVEL_4");
}

const QualityAuditRegisterPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const context = getContext();
  const amoCode = params.amoCode ?? context.amoCode ?? "UNKNOWN";
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = parseQmsRegisterFilters(searchParams);
  const { view: actorView, period, status: findingStatus, stage, timing, auditId, q: search, pageSize, page, level } = filters;
  const [searchDraft, setSearchDraft] = useState(search);
  useEffect(() => setSearchDraft(search), [search]);
  const patchFilters = useCallback((patch: Record<string, string | number | null>, replace = false) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([key, value]) => {
      if (value == null || value === "" || value === "all") next.delete(key);
      else next.set(key, String(value));
    });
    next.delete("tab");
    setSearchParams(next, { replace });
  }, [searchParams, setSearchParams]);
  useEffect(() => {
    // Migrate old cockpit bookmarks into the receiving page's real grammar.
    if (searchParams.get("tab") === "cars") {
      navigate(withQmsQuery(qmsModulePath(amoCode, "cars", timing === "overdue" ? "overdue" : "register"), buildPreservedQmsQuery(searchParams, {}, ["view", "status"])), { replace: true });
    } else if (searchParams.has("tab")) {
      const next = new URLSearchParams(searchParams); next.delete("tab"); setSearchParams(next, { replace: true });
    }
  }, [amoCode, navigate, searchParams, setSearchParams, timing]);
  const canCreateCar = hasQmsRolePermission("qms.car.create");

  const registerQuery = useQuery({
    queryKey: ["qms-assurance-register", amoCode, actorView, period, findingStatus, level, auditId, stage, timing, search, pageSize, page],
    queryFn: ({ signal }) => qmsGetAuditRegisterPage({
      domain: "AMO", view: actorView, period, status: findingStatus || undefined, level: level || undefined,
      auditId: auditId || undefined,
      onlyWithCars: false,
      workflowStage: toRegisterWorkflowStage(stage),
      carTiming: timing || undefined,
      search: search || undefined,
      limit: pageSize,
      offset: (page - 1) * pageSize,
      signal,
    }),
    staleTime: 15_000,
  });

  const rows = useMemo<RegisterRow[]>(() => (registerQuery.data?.rows || []).map((row) => {
    const linkedCars = row.linked_cars || [];
    return {
      id: row.finding.id,
      audit: row.audit,
      finding: row.finding,
      linkedCars,
      lifecycle: findingLifecycleView(row.finding, linkedCars),
      primaryCar: primaryLinkedCar(linkedCars) || null,
    };
  }), [registerQuery.data?.rows]);

  const openFinding = useCallback((row: RegisterRow) => navigate(
    qmsRecordPath(amoCode, "findings", row.finding.id, "overview"),
  ), [amoCode, navigate]);
  const openCorrectiveAction = useCallback((row: RegisterRow) => {
    if (row.primaryCar) {
      navigate(qmsRecordPath(amoCode, "cars", row.primaryCar.id, "overview"));
      return;
    }
    if (canCreateCar && !isObservation(row.finding)) {
      navigate(withQmsQuery(qmsModulePath(amoCode, "cars", "new"), new URLSearchParams({ findingId: row.finding.id })));
      return;
    }
    openFinding(row);
  }, [amoCode, canCreateCar, navigate, openFinding]);

  const columnDefs = useMemo<ColDef<RegisterRow>[]>(() => [
    {
      headerName: "Finding",
      flex: 1.8,
      minWidth: 220,
      cellRenderer: ({ data }: ICellRendererParams<RegisterRow>) => data ? (
        <button type="button" className="qa-register-grid__primary" onClick={() => openFinding(data)}>
          <strong>{data.finding.finding_ref || data.finding.id.slice(0, 8)}</strong>
          <span>{data.finding.description}</span>
        </button>
      ) : null,
    },
    {
      headerName: "Audit",
      flex: 1.2,
      minWidth: 165,
      cellRenderer: ({ data }: ICellRendererParams<RegisterRow>) => data ? (
        <button type="button" className="qa-register-grid__primary" onClick={() => navigate(auditNavigationHref(amoCode, data.audit))}>
          <strong>{data.audit.audit_ref}</strong><span>{data.audit.title}</span>
        </button>
      ) : null,
    },
    {
      headerName: "Class",
      flex: 0.75,
      minWidth: 120,
      valueGetter: ({ data }) => data ? `${humanize(data.finding.level || data.finding.severity)} · ${humanize(data.finding.finding_type)}` : "",
      cellClass: "qa-register-grid__compact-cell",
    },
    {
      headerName: "Corrective action",
      flex: 1.1,
      minWidth: 165,
      cellRenderer: ({ data }: ICellRendererParams<RegisterRow>) => data ? (
        <div className="qa-register-grid__stack">
          <strong>{data.primaryCar?.car_number || (isObservation(data.finding) ? "Observation" : "Pending CAR")}</strong>
          <span>{data.primaryCar ? humanize(data.primaryCar.status) : "No separate action record"}</span>
        </div>
      ) : null,
    },
    {
      headerName: "Owner / due",
      flex: 1,
      minWidth: 150,
      cellRenderer: ({ data }: ICellRendererParams<RegisterRow>) => data ? (
        <div className="qa-register-grid__stack">
          <strong>{data.finding.acknowledged_by_name || data.primaryCar?.responsible_personnel || "Unassigned"}</strong>
          <span>{data.primaryCar?.target_closure_date || data.primaryCar?.due_date || data.finding.target_close_date || "No due date"}</span>
        </div>
      ) : null,
    },
    {
      headerName: "Stage",
      flex: 0.85,
      minWidth: 135,
      cellRenderer: ({ data }: ICellRendererParams<RegisterRow>) => data ? (
        <div className="qa-register-grid__stack">
          <span className={`qa-register-grid__status qa-register-grid__status--${data.lifecycle}`}>{findingLifecycleLabel(data.lifecycle)}</span>
          <small>{findingNextAction(data.lifecycle, Boolean(data.primaryCar))}</small>
        </div>
      ) : null,
    },
    {
      headerName: "Actions",
      pinned: "right",
      width: 92,
      minWidth: 92,
      maxWidth: 92,
      sortable: false,
      cellRenderer: ({ data }: ICellRendererParams<RegisterRow>) => data ? (
        <div className="qa-register-grid__actions">
          <button type="button" title="Open finding" aria-label="Open finding" onClick={() => openFinding(data)}><Search size={15} /></button>
          <button type="button" title={data.primaryCar ? "Open corrective action" : "Continue finding"} aria-label={data.primaryCar ? "Open corrective action" : "Continue finding"} onClick={() => openCorrectiveAction(data)}>
            {data.primaryCar ? <ShieldAlert size={15} /> : <ExternalLink size={15} />}
          </button>
        </div>
      ) : null,
    },
  ], [amoCode, navigate, openCorrectiveAction, openFinding]);

  const defaultColDef = useMemo<ColDef<RegisterRow>>(() => ({
    resizable: true,
    sortable: false,
    suppressMovable: true,
    wrapHeaderText: false,
  }), []);

  const total = registerQuery.data?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const firstVisible = total ? ((page - 1) * pageSize) + 1 : 0;
  const lastVisible = Math.min(total, page * pageSize);
  useEffect(() => {
    if (registerQuery.data && page > totalPages) patchFilters({ page: totalPages }, true);
  }, [page, totalPages, registerQuery.data, patchFilters]);
  const hasFilters = Boolean(auditId || search || stage !== "all" || timing || findingStatus || level || period || actorView === "mine");
  const updateFilter = (key: string, value: string) => patchFilters({ [key]: value, page: null });
  const clearFilters = () => patchFilters({ q: null, stage: null, timing: null, auditId: null, status: null, level: null, period: null, view: null, page: null });
  const auditsHref = withQmsQuery(qmsModulePath(amoCode, "audits", "workspace"), buildPreservedQmsQuery(searchParams));
  const trendsHref = qmsModulePath(amoCode, "reports", "car-performance");

  return (
    <QualityAuditsSectionLayout
      title="Findings & corrective action"
      subtitle="One lifecycle from audit finding through auditee action, Quality review, effectiveness and closure."
    >
      <section className="qa-register-grid-page" aria-label="Findings and corrective action register">
        <header className="qa-register-grid-page__heading">
          <div>
            <span>Follow-up workspace</span>
            <h1>Findings & corrective actions</h1>
            <p>Observations stay as findings. Nonconformities continue in the same row through auditee response, implementation, effectiveness review and closure.</p>
          </div>
          <div className="qa-register-grid-page__heading-actions">
            <button type="button" onClick={() => navigate(auditsHref)}><ClipboardList size={16} /> Open audits</button>
            <button type="button" onClick={() => navigate(trendsHref)}><BarChart3 size={16} /> Finding trends</button>
          </div>
        </header>

        <div className="qa-register-grid-page__metrics" aria-label="Register totals">
          <article><span>Findings</span><strong>{total}</strong><small>Matching this view</small></article>
          <article><span>Linked actions</span><strong>{registerQuery.data?.car_linked_findings ?? "Unavailable"}</strong><small>Findings with a CAR</small></article>
          <article><span>Open actions</span><strong>{registerQuery.data?.open_car_count ?? "Unavailable"}</strong><small>Requiring follow-up</small></article>
        </div>

        <header className="qa-register-grid-page__toolbar">
          <form className="qa-audits-list__search" onSubmit={(event) => { event.preventDefault(); updateFilter("q", searchDraft.trim()); }}>
            <Search size={15} aria-hidden />
            <input aria-label="Search finding, audit, owner or CAR" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="Search finding, audit, owner or CAR" maxLength={160} />
            <button type="submit">Search</button>
          </form>
          <label>Scope <select value={actorView} onChange={(event) => updateFilter("view", event.target.value)}><option value="global">Global</option><option value="mine">My Work</option></select></label>
          <label>Year <input type="number" min={2000} max={2200} value={period ?? ""} placeholder="All years" onChange={(event) => updateFilter("period", event.target.value)} /></label>
          <label>Status <select value={findingStatus} onChange={(event) => updateFilter("status", event.target.value)}><option value="">All</option><option value="open">Open</option><option value="closed">Closed</option></select></label>
          <label>Level <select value={level} onChange={(event) => updateFilter("level", event.target.value)}><option value="">All</option>{[1, 2, 3, 4].map((number) => <option key={number} value={`LEVEL_${number}`}>Level {number}</option>)}</select></label>
          <label>Stage
            <select value={stage} onChange={(event) => updateFilter("stage", event.target.value)}>
              {FINDING_LIFECYCLE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label>Due position
            <select value={timing} onChange={(event) => updateFilter("timing", event.target.value)}>
              <option value="">All due dates</option><option value="overdue">Overdue</option><option value="due_soon">Due in 30 days</option>
            </select>
          </label>
          <div className="qa-register-grid-page__summary">
            {registerQuery.isFetching && !registerQuery.isLoading ? <span className="qa-register-grid-page__refreshing"><RefreshCw size={13} aria-hidden /> Updating</span> : null}
            {hasFilters ? <button type="button" onClick={clearFilters}>Clear filters</button> : null}
          </div>
        </header>

        {registerQuery.isLoading ? (
          <div className="qa-register-grid-page__state" role="status">
            <RefreshCw className="is-spinning" size={24} aria-hidden />
            <strong>Loading findings and actions…</strong>
            <span>Retrieving the tenant-scoped follow-up register.</span>
          </div>
        ) : registerQuery.isError ? (
          <div className="qa-audits-list__state qa-audits-list__state--error" role="alert">
            <strong>Register unavailable.</strong><span>{registerQuery.error instanceof Error ? registerQuery.error.message : "Try again."}</span>
            <button type="button" onClick={() => void registerQuery.refetch()}>Retry</button>
          </div>
        ) : rows.length ? (
          <>
            <div className="qa-register-grid-page__grid ag-theme-alpine" aria-busy={registerQuery.isFetching}>
              <AgGridReact<RegisterRow>
                rowData={rows}
                columnDefs={columnDefs}
                defaultColDef={defaultColDef}
                getRowId={({ data }) => data.id}
                rowHeight={58}
                headerHeight={36}
                animateRows={false}
                onRowDoubleClicked={(event: RowDoubleClickedEvent<RegisterRow>) => event.data && openCorrectiveAction(event.data)}
              />
            </div>

            <footer className="qa-register-grid-page__pagination">
              <span>Showing {firstVisible}–{lastVisible} of {total}</span>
              <label>Rows per page <select value={pageSize} onChange={(event) => { patchFilters({ pageSize: Number(event.target.value) as RegisterPageSize, page: null }); }}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option></select></label>
              <strong>Page {Math.min(page, totalPages)} of {totalPages}</strong>
              <button type="button" title="Previous page" aria-label="Previous page" disabled={page <= 1 || registerQuery.isFetching} onClick={() => patchFilters({ page: Math.max(1, page - 1) })}><ChevronLeft size={16} /></button>
              <button type="button" title="Next page" aria-label="Next page" disabled={!registerQuery.data?.has_more || registerQuery.isFetching} onClick={() => patchFilters({ page: Math.min(totalPages, page + 1) })}><ChevronRight size={16} /></button>
            </footer>
          </>
        ) : (
          <div className="qa-register-grid-page__empty">
            <span className="qa-register-grid-page__empty-icon"><ClipboardCheck size={26} aria-hidden /></span>
            <strong>{hasFilters ? "No records match this view" : "No findings or corrective actions yet"}</strong>
            <p>{hasFilters
              ? "Clear the filters to return to the complete tenant register."
              : "Findings raised during audit fieldwork will appear here. Nonconformities continue into corrective action without creating a duplicate record."}</p>
            <div>
              {hasFilters ? <button type="button" onClick={clearFilters}>Clear filters</button> : null}
              <button type="button" className="is-primary" onClick={() => navigate(auditsHref)}><ClipboardList size={16} /> Open audits</button>
            </div>
          </div>
        )}
      </section>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditRegisterPage;
