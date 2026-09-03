import React, { useCallback, useEffect, useMemo, useRef } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type {
  ColDef,
  GridApi,
  GridReadyEvent,
  ICellRendererParams,
  PaginationChangedEvent,
  RowClickedEvent,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { Activity, CalendarClock, CheckCircle2, CircleUserRound, Search } from "lucide-react";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";
import { ResponsiveSegmentedControl } from "../../components/QMS/ResponsiveSegmentedControl";
import { getCachedUser, getContext } from "../../services/auth";
import {
  getAuditProgramme,
  listAuditProgrammeScheduleLinks,
  listAuditProgrammes,
} from "../../services/qmsAuditProgramme";
import { qmsListAudits, type QMSAuditOut } from "../../services/qmsCore";
import { auditNavigationHref } from "./auditNavigation";
import { auditNextAction } from "./auditNextAction";
import {
  AUDITS_LIST_BOUND,
  attentionLabel,
  buildAuditProgrammeLinkIndex,
  clampWorkspacePage,
  filterWorkspaceAudits,
  formatAuditDate,
  lifecycleLabel,
  parseWorkspacePage,
  parseWorkspacePageSize,
  parseWorkspaceView,
  programmeLabelForAudit,
  WORKSPACE_PAGE_SIZES,
  type WorkspacePageSize,
  type WorkspaceView,
} from "./auditsWorkspaceModel";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import "./quality-audits-list-workspace.css";

type AuditGridRow = QMSAuditOut & {
  programmeLabel: string;
  typeLabel: string;
  scheduledLabel: string;
  stageLabel: string;
  attentionText: string;
  nextActionLabel: string;
  nextActionHref: string;
};

function AuditIdentityCell(params: ICellRendererParams<AuditGridRow>) {
  const row = params.data;
  if (!row) return null;
  return (
    <Link className="qa-audits-grid__identity qa-audits-grid__identity-link" to={row.nextActionHref}>
      <span className="qa-audits-list__ref">{row.audit_ref}</span>
      <strong>{row.title}</strong>
    </Link>
  );
}

function AttentionCell(params: ICellRendererParams<AuditGridRow>) {
  const text = params.data?.attentionText;
  if (!text) return <span className="qa-audits-grid__muted">—</span>;
  return <span className="qa-audits-list__attention">{text}</span>;
}

function StageCell(params: ICellRendererParams<AuditGridRow>) {
  const row = params.data;
  if (!row) return null;
  return (
    <span className={`qa-audits-list__status qa-audits-list__status--${row.status.toLowerCase()}`}>
      {row.stageLabel}
    </span>
  );
}

function NextActionCell(params: ICellRendererParams<AuditGridRow>) {
  const row = params.data;
  if (!row) return null;
  return (
    <Link className="qa-audits-list__action" to={row.nextActionHref}>
      {row.nextActionLabel}
    </Link>
  );
}

const QualityAuditsWorkspacePage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const context = getContext();
  const amoCode = params.amoCode ?? context.amoCode ?? "UNKNOWN";
  const currentUser = getCachedUser();
  const gridApiRef = useRef<GridApi<AuditGridRow> | null>(null);
  const syncingPaginationRef = useRef(false);

  const view = parseWorkspaceView(searchParams.get("view"));
  const search = searchParams.get("q") ?? "";
  const pageSize = parseWorkspacePageSize(searchParams.get("pageSize"));
  const pageFromUrl = parseWorkspacePage(searchParams.get("page"));

  const patchParams = useCallback(
    (patch: Record<string, string | null>, replace = true) => {
      const next = new URLSearchParams(searchParams);
      for (const [key, value] of Object.entries(patch)) {
        if (value == null || value === "") next.delete(key);
        else next.set(key, value);
      }
      setSearchParams(next, { replace });
    },
    [searchParams, setSearchParams],
  );

  const setView = (nextView: WorkspaceView) => {
    patchParams({
      view: nextView === "mine" ? null : nextView,
      page: null,
    });
  };

  const auditsQuery = useQuery({
    queryKey: ["qms-audits-workspace", amoCode],
    queryFn: () => qmsListAudits({ domain: "AMO", limit: AUDITS_LIST_BOUND }),
    staleTime: 30_000,
  });

  const programmeYear = new Date().getUTCFullYear();
  const programmesQuery = useQuery({
    queryKey: ["qms-audits-workspace-programmes", amoCode, programmeYear],
    queryFn: ({ signal }) => listAuditProgrammes(amoCode, programmeYear, signal),
    staleTime: 60_000,
  });
  const programmeSummaries = programmesQuery.data?.items ?? [];

  const programmeDetailQueries = useQueries({
    queries: programmeSummaries.map((programme) => ({
      queryKey: ["qms-audit-programme", amoCode, programme.id],
      queryFn: ({ signal }: { signal?: AbortSignal }) => getAuditProgramme(amoCode, programme.id, signal),
      staleTime: 60_000,
      enabled: Boolean(programme.id),
    })),
  });

  const scheduleLinkQueries = useQueries({
    queries: programmeSummaries.map((programme) => ({
      queryKey: ["qms-audit-programme-schedule-links", amoCode, programme.id],
      queryFn: ({ signal }: { signal?: AbortSignal }) =>
        listAuditProgrammeScheduleLinks(amoCode, programme.id, signal),
      staleTime: 60_000,
      enabled: Boolean(programme.id),
    })),
  });

  const programmeIndex = useMemo(() => {
    const detailed = programmeDetailQueries
      .map((query) => query.data)
      .filter((programme): programme is NonNullable<typeof programme> => Boolean(programme));
    if (!detailed.length && !programmeSummaries.length) {
      return buildAuditProgrammeLinkIndex([], new Map());
    }
    const programmes = detailed.length ? detailed : programmeSummaries;
    const linksByProgrammeId = new Map(
      programmeSummaries.map((programme, index) => [
        programme.id,
        scheduleLinkQueries[index]?.data?.items ?? [],
      ]),
    );
    return buildAuditProgrammeLinkIndex(programmes, linksByProgrammeId);
  }, [programmeDetailQueries, programmeSummaries, scheduleLinkQueries]);

  const filteredAudits = useMemo(
    () =>
      filterWorkspaceAudits(auditsQuery.data ?? [], {
        view,
        userId: currentUser?.id,
        search,
        programmeIndex,
      }),
    [auditsQuery.data, currentUser?.id, programmeIndex, search, view],
  );

  const safePage = clampWorkspacePage(pageFromUrl, filteredAudits.length, pageSize);

  useEffect(() => {
    if (safePage !== pageFromUrl) {
      patchParams({ page: safePage <= 1 ? null : String(safePage) });
    }
  }, [pageFromUrl, patchParams, safePage]);

  const rowData = useMemo<AuditGridRow[]>(
    () =>
      filteredAudits.map((audit) => {
        const action = auditNextAction(audit);
        const href = auditNavigationHref(amoCode, audit);
        return {
          ...audit,
          programmeLabel: programmeLabelForAudit(audit, programmeIndex),
          typeLabel: audit.kind.replaceAll("_", " ").toLowerCase(),
          scheduledLabel: `${formatAuditDate(audit.planned_start)} – ${formatAuditDate(audit.planned_end)}`,
          stageLabel: lifecycleLabel(audit.status),
          attentionText: attentionLabel(audit) ?? "",
          nextActionLabel: action.label,
          nextActionHref: href,
        };
      }),
    [amoCode, filteredAudits, programmeIndex],
  );

  const columnDefs = useMemo<ColDef<AuditGridRow>[]>(
    () => [
      {
        headerName: "Audit",
        field: "audit_ref",
        colId: "audit",
        pinned: "left",
        minWidth: 200,
        flex: 1.4,
        cellRenderer: AuditIdentityCell,
        comparator: (_a, _b, nodeA, nodeB) =>
          (nodeA?.data?.audit_ref || "").localeCompare(nodeB?.data?.audit_ref || ""),
      },
      {
        headerName: "Programme",
        field: "programmeLabel",
        minWidth: 110,
        flex: 0.9,
      },
      {
        headerName: "Type",
        field: "typeLabel",
        minWidth: 100,
        flex: 0.7,
        valueFormatter: (p) =>
          p.value ? String(p.value).replace(/\b\w/g, (ch: string) => ch.toUpperCase()) : "",
      },
      {
        headerName: "Scheduled",
        field: "scheduledLabel",
        colId: "scheduled",
        minWidth: 150,
        flex: 1,
        comparator: (_a, _b, nodeA, nodeB) => {
          const left = nodeA?.data?.planned_start || "";
          const right = nodeB?.data?.planned_start || "";
          return left.localeCompare(right);
        },
      },
      {
        headerName: "Lead",
        field: "lead_auditor_name",
        minWidth: 120,
        flex: 0.9,
        valueFormatter: (p) => p.value || "Not assigned",
      },
      {
        headerName: "Stage",
        field: "stageLabel",
        minWidth: 120,
        flex: 0.8,
        cellRenderer: StageCell,
      },
      {
        headerName: "Attention",
        field: "attentionText",
        minWidth: 140,
        flex: 0.9,
        cellRenderer: AttentionCell,
      },
      {
        headerName: "Next action",
        field: "nextActionLabel",
        colId: "nextAction",
        minWidth: 150,
        flex: 0.95,
        sortable: false,
        cellRenderer: NextActionCell,
      },
    ],
    [],
  );

  const defaultColDef = useMemo<ColDef<AuditGridRow>>(
    () => ({
      sortable: true,
      resizable: true,
      flex: 1,
      minWidth: 96,
      suppressMovable: true,
    }),
    [],
  );

  const syncGridPagination = useCallback(
    (api: GridApi<AuditGridRow>) => {
      syncingPaginationRef.current = true;
      const currentSize = api.paginationGetPageSize();
      if (currentSize !== pageSize) {
        api.setGridOption("paginationPageSize", pageSize);
      }
      const zeroBased = safePage - 1;
      if (api.paginationGetCurrentPage() !== zeroBased) {
        api.paginationGoToPage(zeroBased);
      }
      window.setTimeout(() => {
        syncingPaginationRef.current = false;
      }, 0);
    },
    [pageSize, safePage],
  );

  const onGridReady = useCallback(
    (event: GridReadyEvent<AuditGridRow>) => {
      gridApiRef.current = event.api;
      syncGridPagination(event.api);
    },
    [syncGridPagination],
  );

  useEffect(() => {
    const api = gridApiRef.current;
    if (!api) return;
    syncGridPagination(api);
  }, [rowData, syncGridPagination]);

  const onPaginationChanged = useCallback(
    (event: PaginationChangedEvent<AuditGridRow>) => {
      if (syncingPaginationRef.current || !event.api) return;
      const nextPage = event.api.paginationGetCurrentPage() + 1;
      const nextSize = event.api.paginationGetPageSize() as WorkspacePageSize;
      const normalizedSize = WORKSPACE_PAGE_SIZES.includes(nextSize) ? nextSize : pageSize;
      patchParams({
        page: nextPage <= 1 ? null : String(nextPage),
        pageSize: normalizedSize === 25 ? null : String(normalizedSize),
      });
    },
    [pageSize, patchParams],
  );

  const onRowClicked = useCallback(
    (event: RowClickedEvent<AuditGridRow>) => {
      const target = event.event?.target;
      if (target instanceof Element && target.closest("a, button")) return;
      const href = event.data?.nextActionHref;
      if (href) navigate(href);
    },
    [navigate],
  );

  const loadedCount = auditsQuery.data?.length ?? 0;
  const boundHit = loadedCount >= AUDITS_LIST_BOUND;

  return (
    <QualityAuditsSectionLayout
      title="Audits"
      subtitle="Open the audit that needs attention and continue from its current lifecycle stage."
      toolbar={
        <ResponsiveSegmentedControl
          label="Audit workspace view"
          value={view}
          onChange={setView}
          compactIconsOnMobile
          options={[
            { value: "mine", label: "MY AUDITS", shortLabel: "Mine", icon: CircleUserRound },
            { value: "upcoming", label: "UPCOMING", shortLabel: "Upcoming", icon: CalendarClock },
            { value: "active", label: "ACTIVE", shortLabel: "Active", icon: Activity },
            { value: "completed", label: "COMPLETED", shortLabel: "Completed", icon: CheckCircle2 },
          ]}
        />
      }
    >
      <section className="qa-audits-list qa-audits-list--register" aria-live="polite">
        <header className="qa-audits-list__toolbar">
          <div className="qa-audits-list__summary">
            <div>
              <strong>{filteredAudits.length}</strong>
              <span>{view === "mine" ? "assigned audits" : `${view} audits`}</span>
            </div>
            <small>
              Client page of up to {AUDITS_LIST_BOUND} current tenant records
              {boundHit ? " (bound reached)" : ""}. Opening an audit does not change its lifecycle.
            </small>
          </div>
          <label className="qa-audits-list__search" aria-label="Search audits">
            <Search size={15} aria-hidden />
            <input
              value={search}
              onChange={(event) => {
                patchParams({
                  q: event.target.value || null,
                  page: null,
                });
              }}
              placeholder="Search audits"
            />
          </label>
        </header>

        {auditsQuery.isError ? (
          <div className="qa-audits-list__state qa-audits-list__state--error" role="alert">
            <strong>Audits could not be loaded.</strong>
            <span>Check your connection, then try again.</span>
            <button type="button" onClick={() => void auditsQuery.refetch()}>
              Retry
            </button>
          </div>
        ) : null}

        <div className="qa-audits-list__grid-shell ag-theme-alpine">
          <AgGridReact<AuditGridRow>
            rowData={auditsQuery.isError ? [] : rowData}
            columnDefs={columnDefs}
            defaultColDef={defaultColDef}
            getRowId={(row) => row.data.id}
            rowHeight={40}
            headerHeight={36}
            animateRows={false}
            suppressCellFocus
            pagination
            paginationPageSize={pageSize}
            paginationPageSizeSelector={[...WORKSPACE_PAGE_SIZES]}
            onGridReady={onGridReady}
            onPaginationChanged={onPaginationChanged}
            onRowClicked={onRowClicked}
            rowClass="qa-audits-grid__row"
            loading={auditsQuery.isLoading}
            overlayLoadingTemplate='<span class="qa-audits-grid__overlay">Loading audits…</span>'
            overlayNoRowsTemplate='<span class="qa-audits-grid__overlay"><strong>No audits in this view</strong><br/>Choose another view, clear search, or schedule from Calendar.</span>'
            domLayout="normal"
            containerStyle={{ width: "100%", height: "100%" }}
          />
        </div>
      </section>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditsWorkspacePage;
