import React, {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import type {
  ColDef,
  ICellRendererParams,
  RowClickedEvent,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import {
  Activity,
  AlertTriangle,
  CalendarClock,
  CalendarPlus,
  CheckCircle2,
  CircleUserRound,
  ListChecks,
  Search,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";
import { ResponsiveSegmentedControl } from "../../components/QMS/ResponsiveSegmentedControl";
import { useToast } from "../../components/feedback/ToastProvider";
import { getContext } from "../../services/auth";
import { hasQmsRolePermission } from "../../app/routeGuards";
import {
  addAuditProgrammeItem,
  createAuditUniverseItem,
  getAuditProgramme,
  listAuditUniverse,
  listAuditProgrammeScheduleLinks,
  listAuditProgrammes,
  type AuditProgramme,
  type AuditUniverseEntityType,
} from "../../services/qmsAuditProgramme";
import {
  qmsDeleteAudit,
  qmsListAudits,
  qmsListAllAudits,
  type QMSAuditListParams,
  type QMSAuditOut,
} from "../../services/qmsCore";
import { auditNavigationHref } from "./auditNavigation";
import { auditNextAction } from "./auditNextAction";
import AuditLaunchDrawer, { type AuditLaunchMode } from "./AuditLaunchDrawer";
import { workingDayCount } from "../qms/qmsAuditProgrammePlanning";
import {
  attentionLabel,
  buildAuditProgrammeLinkIndex,
  clampWorkspacePage,
  formatAuditDate,
  lifecycleLabel,
  parseWorkspacePage,
  parseWorkspacePageSize,
  parseWorkspaceView,
  programmeLabelForAudit,
  WORKSPACE_PAGE_SIZES,
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

const AUDIT_DELETE_FAILURE_MESSAGE =
  "The audit could not be moved to the recycle bin. No records were changed. Try again; if the problem continues, contact an administrator.";

type ProgrammePrompt = {
  audit: QMSAuditOut;
};

function AuditIdentityCell(params: ICellRendererParams<AuditGridRow>) {
  const row = params.data;
  if (!row) return null;
  return (
    <Link
      className="qa-audits-grid__identity qa-audits-grid__identity-link"
      to={row.nextActionHref}
    >
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
    <span
      className={`qa-audits-list__status qa-audits-list__status--${row.status.toLowerCase()}`}
    >
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
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const context = getContext();
  const amoCode = params.amoCode ?? context.amoCode ?? "UNKNOWN";
  const canDeleteAudit = hasQmsRolePermission("qms.audit.manage");
  const canCreateAudit = hasQmsRolePermission("qms.audit.manage");
  const [launchMode, setLaunchMode] = useState<AuditLaunchMode | null>(null);
  const [programmePrompt, setProgrammePrompt] =
    useState<ProgrammePrompt | null>(null);
  const [programmePromptError, setProgrammePromptError] = useState<
    string | null
  >(null);
  const [targetProgrammeId, setTargetProgrammeId] = useState("");
  const [targetUniverseId, setTargetUniverseId] = useState("__new__");
  const [newUniverseLabel, setNewUniverseLabel] = useState("");
  const [newUniverseType, setNewUniverseType] =
    useState<AuditUniverseEntityType>("DEPARTMENT");
  const [deleteTarget, setDeleteTarget] = useState<QMSAuditOut | null>(null);
  const [deleteReason, setDeleteReason] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const view = parseWorkspaceView(searchParams.get("view"));
  const search = searchParams.get("q") ?? "";
  const pageSize = parseWorkspacePageSize(searchParams.get("pageSize"));
  const sort = (searchParams.get("sort") || (view === "completed" ? "actual_end" : "planned_start")) as QMSAuditListParams["sort"];
  const direction = searchParams.get("direction") === "desc" || (!searchParams.has("direction") && view === "completed") ? "desc" : "asc";
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
      view: nextView === "all" ? null : nextView,
      page: null,
    });
  };

  const auditsQuery = useQuery({
    queryKey: ["qms-audits-workspace", amoCode, view, search, sort, direction, pageFromUrl, pageSize, searchParams.get("period"), searchParams.get("status")],
    queryFn: () => qmsListAudits({ domain: "AMO", limit: pageSize, offset: (pageFromUrl - 1) * pageSize,
      view, q: search, period: searchParams.get("period") ? Number(searchParams.get("period")) : undefined,
      status_: (searchParams.get("status") || undefined) as QMSAuditOut["status"] | undefined,
      sort, direction }, { amoCode }),
    staleTime: 30_000,
  });

  const launchAuditsQuery = useQuery({
    queryKey: ["qms-audits-launch-collection", amoCode],
    queryFn: () => qmsListAllAudits({ domain: "AMO" }, { amoCode }),
    enabled: Boolean(launchMode),
  });

  const programmeYear = new Date().getUTCFullYear();
  const programmesQuery = useQuery({
    queryKey: ["qms-audits-workspace-programmes", amoCode, programmeYear],
    queryFn: ({ signal }) =>
      listAuditProgrammes(amoCode, programmeYear, signal),
    staleTime: 60_000,
  });
  const programmeSummaries = useMemo(
    () => programmesQuery.data?.items ?? [],
    [programmesQuery.data?.items],
  );

  const programmeDetailQueries = useQueries({
    queries: programmeSummaries.map((programme) => ({
      queryKey: ["qms-audit-programme", amoCode, programme.id],
      queryFn: ({ signal }: { signal?: AbortSignal }) =>
        getAuditProgramme(amoCode, programme.id, signal),
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

  const programmeDetails = useMemo<AuditProgramme[]>(
    () =>
      programmeDetailQueries
        .map((query) => query.data)
        .filter((programme): programme is AuditProgramme => Boolean(programme)),
    [programmeDetailQueries],
  );

  const programmeIndex = useMemo(() => {
    if (!programmeDetails.length && !programmeSummaries.length) {
      return buildAuditProgrammeLinkIndex([], new Map());
    }
    const programmes = programmeDetails.length
      ? programmeDetails
      : programmeSummaries;
    const linksByProgrammeId = new Map(
      programmeSummaries.map((programme, index) => [
        programme.id,
        scheduleLinkQueries[index]?.data?.items ?? [],
      ]),
    );
    return buildAuditProgrammeLinkIndex(programmes, linksByProgrammeId);
  }, [programmeDetails, programmeSummaries, scheduleLinkQueries]);

  const filteredAudits = auditsQuery.data?.items ?? [];
  const editableProgrammes = useMemo(
    () =>
      programmeDetails.filter((programme) =>
        ["DRAFT", "UNDER_REVIEW"].includes(programme.status),
      ),
    [programmeDetails],
  );
  const compatibleProgrammeTargets = useMemo(
    () =>
      programmePrompt
        ? editableProgrammes.filter(
            (programme) =>
              (programme.programme_kind || "INTERNAL") ===
              programmePrompt.audit.kind,
          )
        : [],
    [editableProgrammes, programmePrompt],
  );
  const universeQuery = useQuery({
    queryKey: ["qms-audit-universe", amoCode],
    queryFn: ({ signal }) => listAuditUniverse(amoCode, signal),
    staleTime: 60_000,
    enabled: Boolean(programmePrompt),
  });

  const addToProgrammeMutation = useMutation({
    mutationFn: async () => {
      const audit = programmePrompt?.audit;
      const programme = compatibleProgrammeTargets.find(
        (entry) => entry.id === targetProgrammeId,
      );
      if (!audit || !programme)
        throw new Error("Select an editable audit programme.");
      if (!audit.planned_start)
        throw new Error("The audit needs a planned date before it can recur.");

      let universeItemId = targetUniverseId;
      if (targetUniverseId === "__new__") {
        if (newUniverseLabel.trim().length < 2)
          throw new Error("Enter a coverage area name.");
        const universeItem = await createAuditUniverseItem(amoCode, {
          entity_type: newUniverseType,
          display_label: newUniverseLabel.trim(),
          source_owner_module: "QUALITY",
          source_type: "AUDIT_OCCURRENCE",
          source_id: audit.id,
          source_route: auditNavigationHref(amoCode, audit),
          risk_classification: "MEDIUM",
          regulatory_criticality: "MEDIUM",
          mandatory_surveillance: false,
          notes: `Coverage created from ${audit.audit_ref}.`,
        });
        universeItemId = universeItem.id;
      }
      if (!universeItemId || universeItemId === "__new__")
        throw new Error("Select a coverage area.");

      const monthDay = audit.planned_start.slice(5);
      return addAuditProgrammeItem(amoCode, programme.id, {
        universe_item_id: universeItemId,
        audit_type:
          audit.kind === "INTERNAL"
            ? "INTERNAL"
            : audit.kind === "THIRD_PARTY"
              ? "REGULATORY"
              : "SUPPLIER",
        title: audit.title,
        purpose: `Recurring assurance requirement created from ${audit.audit_ref}.`,
        scope: audit.scope?.trim() || audit.title,
        criteria: audit.criteria?.trim() ? [audit.criteria.trim()] : [],
        mandatory_surveillance: false,
        recurrence: "FIXED_DATES",
        fixed_dates: [monthDay],
        non_working_day_policy: "NEXT_WORKING_DAY",
        default_start_time: audit.planned_start_time?.slice(0, 5) || "09:00",
        default_end_time: audit.planned_end_time?.slice(0, 5) || "17:00",
        default_duration_days: workingDayCount(
          audit.planned_start,
          audit.planned_end,
        ),
        default_location: audit.location || undefined,
        lead_auditor_user_id: audit.lead_auditor_user_id || undefined,
        observer_auditor_user_id: audit.observer_auditor_user_id || undefined,
        supporting_auditor_user_ids: audit.supporting_auditor_user_ids || [],
        auditee_user_id: audit.auditee_user_id || undefined,
        notify_auditors: audit.notify_auditors ?? true,
        notify_auditees: audit.notify_auditees ?? true,
        auto_schedule: true,
        prioritization_basis: [
          {
            driver: "DIRECT_AUDIT_REUSE",
            source_audit_id: audit.id,
            source_audit_ref: audit.audit_ref,
          },
        ],
      });
    },
    onSuccess: async () => {
      const audit = programmePrompt?.audit;
      setProgrammePrompt(null);
      setProgrammePromptError(null);
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["qms-audits-workspace-programmes", amoCode],
        }),
        queryClient.invalidateQueries({
          queryKey: ["qms-audit-universe", amoCode],
        }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-programme"] }),
      ]);
      pushToast({
        title: "Added to audit programme",
        message:
          "The audit will recur on this calendar date; weekends move to the next working day.",
        variant: "success",
      });
      if (audit) navigate(auditNavigationHref(amoCode, audit));
    },
    onError: (reason: Error) =>
      setProgrammePromptError(
        reason.message || "The audit could not be added to the programme.",
      ),
  });

  const safePage = clampWorkspacePage(
    pageFromUrl,
    auditsQuery.data?.total ?? pageFromUrl * pageSize,
    pageSize,
  );

  const deleteMutation = useMutation({
    mutationFn: ({ auditId, reason }: { auditId: string; reason?: string }) =>
      qmsDeleteAudit(auditId, reason),
    onSuccess: (_result, variables) => {
      setDeleteTarget(null);
      setDeleteReason("");
      setDeleteError(null);
      void queryClient.invalidateQueries({
        queryKey: ["qms-audits-workspace", amoCode],
      });
    },
    onError: () => setDeleteError(AUDIT_DELETE_FAILURE_MESSAGE),
  });

  useEffect(() => {
    if (!deleteTarget || deleteMutation.isPending) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDeleteTarget(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [deleteMutation.isPending, deleteTarget]);

  const requestDelete = useCallback((audit: QMSAuditOut) => {
    setDeleteTarget(audit);
    setDeleteReason("");
    setDeleteError(null);
  }, []);

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
        const programmeLabel = programmeLabelForAudit(audit, programmeIndex);
        return {
          ...audit,
          programmeLabel:
            programmeLabel === "Direct audit" ? "One-off" : programmeLabel,
          typeLabel: audit.title
            .trim()
            .toLowerCase()
            .startsWith("surveillance ·")
            ? "Surveillance"
            : "Scheduled audit",
          scheduledLabel:
            `${formatAuditDate(audit.planned_start)} ${audit.planned_start_time?.slice(0, 5) || ""} – ${formatAuditDate(audit.planned_end)} ${audit.planned_end_time?.slice(0, 5) || ""}`
              .replaceAll("  ", " ")
              .trim(),
          stageLabel: lifecycleLabel(audit.status, audit),
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
        minWidth: 220,
        flex: 1.5,
        wrapText: true,
        autoHeight: true,
        cellRenderer: AuditIdentityCell,
        comparator: (_a, _b, nodeA, nodeB) =>
          (nodeA?.data?.audit_ref || "").localeCompare(
            nodeB?.data?.audit_ref || "",
          ),
      },
      {
        headerName: "Source",
        field: "programmeLabel",
        minWidth: 110,
        flex: 0.9,
      },
      {
        headerName: "Activity",
        field: "typeLabel",
        minWidth: 100,
        flex: 0.7,
        valueFormatter: (p) =>
          p.value
            ? String(p.value).replace(/\b\w/g, (ch: string) => ch.toUpperCase())
            : "",
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
      {
        headerName: "",
        colId: "delete",
        pinned: "right",
        width: 54,
        minWidth: 54,
        maxWidth: 54,
        sortable: false,
        resizable: false,
        suppressHeaderMenuButton: true,
        cellRenderer: (params: ICellRendererParams<AuditGridRow>) =>
          params.data && canDeleteAudit ? (
            <button
              type="button"
              className="qa-audits-list__delete"
              aria-label={`Delete ${params.data.audit_ref} ${params.data.title}`}
              title="Delete audit and associated records"
              onClick={() => requestDelete(params.data!)}
            >
              <Trash2 size={15} aria-hidden />
            </button>
          ) : null,
      },
    ],
    [canDeleteAudit, requestDelete],
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

  const onRowClicked = useCallback(
    (event: RowClickedEvent<AuditGridRow>) => {
      const target = event.event?.target;
      if (target instanceof Element && target.closest("a, button")) return;
      const href = event.data?.nextActionHref;
      if (href) navigate(href);
    },
    [navigate],
  );

  const openAudit = useCallback(
    (audit: QMSAuditOut) => {
      setLaunchMode(null);
      navigate(auditNavigationHref(amoCode, audit));
    },
    [amoCode, navigate],
  );

  const handleAuditCreated = useCallback(
    (audit: QMSAuditOut, creation: { offerProgramme: boolean }) => {
      void queryClient.invalidateQueries({ queryKey: ["qms-audits-launch-collection", amoCode] });
      void queryClient.invalidateQueries({
        queryKey: ["qms-audits-workspace", amoCode],
      });
      setLaunchMode(null);
      pushToast({
        title:
          audit.status === "IN_PROGRESS"
            ? "Surveillance started"
            : "Audit created",
        message:
          audit.status === "IN_PROGRESS"
            ? `${audit.audit_ref} is open in fieldwork.`
            : `${audit.audit_ref} is ready for setup and preparation.`,
        variant: "success",
        sound: true,
      });
      if (creation.offerProgramme) {
        const compatible = editableProgrammes.find(
          (programme) =>
            (programme.programme_kind || "INTERNAL") === audit.kind,
        );
        setTargetProgrammeId(compatible?.id || "");
        setTargetUniverseId("__new__");
        setNewUniverseLabel(
          audit.auditee_user_name || audit.auditee || audit.title,
        );
        setNewUniverseType(
          audit.audit_scope_code === "MO" ? "FACILITY" : "DEPARTMENT",
        );
        setProgrammePromptError(null);
        setProgrammePrompt({ audit });
        return;
      }
      navigate(auditNavigationHref(amoCode, audit));
    },
    [amoCode, editableProgrammes, navigate, pushToast, queryClient],
  );

  return (
    <QualityAuditsSectionLayout
      title="Audits"
      subtitle="Create, conduct, and close scheduled audits or unscheduled surveillance."
    >
      <section
        className="qa-audits-list qa-audits-list--register"
        aria-live="polite"
      >
        <div className="qa-audits-list__view-bar">
          <ResponsiveSegmentedControl
            label="Audit workspace view"
            value={view}
            onChange={setView}
            compactIconsOnMobile
            options={[
              {
                value: "all",
                label: "ALL AUDITS",
                shortLabel: "All",
                icon: ListChecks,
              },
              {
                value: "mine",
                label: "MY AUDITS",
                shortLabel: "Mine",
                icon: CircleUserRound,
              },
              {
                value: "upcoming",
                label: "UPCOMING",
                shortLabel: "Upcoming",
                icon: CalendarClock,
              },
              {
                value: "active",
                label: "ACTIVE",
                shortLabel: "Active",
                icon: Activity,
              },
              {
                value: "completed",
                label: "COMPLETED",
                shortLabel: "Completed",
                icon: CheckCircle2,
              },
            ]}
          />
        </div>
        <header className="qa-audits-list__toolbar">
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
          <label className="qa-audits-list__filter">
            Sort
            <select
              value={sort}
              onChange={(event) =>
                patchParams({ sort: event.target.value, page: null })
              }
            >
              <option value="planned_start">Scheduled date</option>
              <option value="actual_end">Completion date</option>
              <option value="audit_ref">Reference</option>
              <option value="title">Title</option>
              <option value="created_at">Created</option>
            </select>
          </label>
          <label className="qa-audits-list__filter">
            Order
            <select
              value={direction}
              onChange={(event) =>
                patchParams({ direction: event.target.value, page: null })
              }
            >
              <option value="asc">Ascending</option>
              <option value="desc">Descending</option>
            </select>
          </label>
          {canCreateAudit ? (
            <div
              className="qa-audits-list__create-actions"
              aria-label="Create assurance activity"
            >
              <button
                type="button"
                className="qa-audits-list__create qa-audits-list__create--secondary"
                onClick={() => setLaunchMode("surveillance")}
              >
                <ShieldCheck size={16} aria-hidden /> Surveillance
              </button>
              <button
                type="button"
                className="qa-audits-list__create"
                onClick={() => setLaunchMode("audit")}
              >
                <CalendarPlus size={16} aria-hidden /> Audit
              </button>
            </div>
          ) : null}
        </header>

        {auditsQuery.isError ? (
          <div
            className="qa-audits-list__state qa-audits-list__state--error"
            role="alert"
          >
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
            defaultColDef={{ ...defaultColDef, sortable: false }}
            getRowId={(row) => row.data.id}
            headerHeight={38}
            animateRows={false}
            suppressCellFocus
            onRowClicked={onRowClicked}
            rowClass="qa-audits-grid__row"
            loading={auditsQuery.isLoading}
            overlayLoadingTemplate='<span class="qa-audits-grid__overlay">Loading audits…</span>'
            overlayNoRowsTemplate='<span class="qa-audits-grid__overlay"><strong>No audits in this view</strong><br/>Create a scheduled audit or start surveillance.</span>'
            domLayout="normal"
            containerStyle={{ width: "100%", height: "100%" }}
          />
        </div>
        <nav className="qa-audits-list__pager" aria-label="Audit result pages">
          <span className="qa-audits-list__pager-meta">
            {auditsQuery.data?.total ?? 0} results · Page {safePage}
          </span>
          <button
            type="button"
            disabled={safePage <= 1 || auditsQuery.isFetching}
            onClick={() => patchParams({ page: String(safePage - 1) })}
          >
            Previous
          </button>
          <button
            type="button"
            disabled={
              !auditsQuery.data ||
              safePage * pageSize >= auditsQuery.data.total ||
              auditsQuery.isFetching
            }
            onClick={() => patchParams({ page: String(safePage + 1) })}
          >
            Next
          </button>
          <label className="qa-audits-list__filter">
            Results per page
            <select
              value={pageSize}
              onChange={(event) =>
                patchParams({ pageSize: event.target.value, page: null })
              }
            >
              {WORKSPACE_PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        </nav>
      </section>
      {launchMode && launchAuditsQuery.isLoading ? <p role="status">Loading existing audits...</p> : null}
      {launchMode && launchAuditsQuery.isError ? <p role="alert">Existing audits could not be loaded. <button onClick={() => void launchAuditsQuery.refetch()}>Retry</button></p> : null}
      {launchMode && launchAuditsQuery.data ? (
        <AuditLaunchDrawer
          key={launchMode}
          amoCode={amoCode}
          isOpen
          mode={launchMode}
          programmes={
            programmeDetails.length ? programmeDetails : programmeSummaries
          }
          existingAudits={launchAuditsQuery.data || []}
          onClose={() => setLaunchMode(null)}
          onCreated={handleAuditCreated}
          onOpenExisting={openAudit}
        />
      ) : null}
      {programmePrompt ? (
        <div
          className="qa-audit-programme-prompt"
          role="presentation"
          onMouseDown={() =>
            !addToProgrammeMutation.isPending && setProgrammePrompt(null)
          }
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="qa-audit-programme-prompt-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <CalendarPlus size={19} aria-hidden />
                <h2 id="qa-audit-programme-prompt-title">
                  Schedule this audit automatically next time?
                </h2>
              </div>
              <button
                type="button"
                aria-label="Close"
                disabled={addToProgrammeMutation.isPending}
                onClick={() => setProgrammePrompt(null)}
              >
                <X size={18} />
              </button>
            </header>
            <p>
              Add{" "}
              <strong>
                {programmePrompt.audit.audit_ref} ·{" "}
                {programmePrompt.audit.title}
              </strong>{" "}
              to the annual programme. It will recur every year on{" "}
              <strong>{programmePrompt.audit.planned_start?.slice(5)}</strong>;
              weekend dates move to the next working day.
            </p>
            {compatibleProgrammeTargets.length ? (
              <div className="qa-audit-programme-prompt__form">
                <label>
                  Audit programme
                  <select
                    value={targetProgrammeId}
                    onChange={(event) =>
                      setTargetProgrammeId(event.target.value)
                    }
                  >
                    {compatibleProgrammeTargets.map((programme) => (
                      <option key={programme.id} value={programme.id}>
                        {programme.programme_ref} · {programme.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Coverage area
                  <select
                    value={targetUniverseId}
                    onChange={(event) =>
                      setTargetUniverseId(event.target.value)
                    }
                    disabled={universeQuery.isLoading}
                  >
                    <option value="__new__">
                      Create coverage area from this audit
                    </option>
                    {(universeQuery.data?.items || [])
                      .filter((item) => item.active)
                      .map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.display_label} ·{" "}
                          {item.entity_type.replaceAll("_", " ").toLowerCase()}
                        </option>
                      ))}
                  </select>
                </label>
                {targetUniverseId === "__new__" ? (
                  <div className="qa-audit-programme-prompt__grid">
                    <label>
                      Coverage name
                      <input
                        value={newUniverseLabel}
                        onChange={(event) =>
                          setNewUniverseLabel(event.target.value)
                        }
                      />
                    </label>
                    <label>
                      Coverage type
                      <select
                        value={newUniverseType}
                        onChange={(event) =>
                          setNewUniverseType(
                            event.target.value as AuditUniverseEntityType,
                          )
                        }
                      >
                        <option value="DEPARTMENT">Department</option>
                        <option value="FACILITY">Facility / hangar</option>
                        <option value="STATION">Line station</option>
                        <option value="PROCESS">Process</option>
                        <option value="CAPABILITY">Capability</option>
                        <option value="SUPPLIER">Supplier</option>
                        <option value="OTHER">Other</option>
                      </select>
                    </label>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="qa-audit-programme-prompt__empty">
                <strong>No editable programme is available.</strong>
                <span>
                  Create or amend this year’s programme before adding
                  recurrence.
                </span>
              </div>
            )}
            {programmePromptError ? (
              <p className="qa-audit-programme-prompt__error" role="alert">
                {programmePromptError}
              </p>
            ) : null}
            <footer>
              <button
                type="button"
                disabled={addToProgrammeMutation.isPending}
                onClick={() => {
                  const audit = programmePrompt.audit;
                  setProgrammePrompt(null);
                  navigate(auditNavigationHref(amoCode, audit));
                }}
              >
                Keep as one-off
              </button>
              {compatibleProgrammeTargets.length ? (
                <button
                  type="button"
                  className="is-primary"
                  disabled={
                    addToProgrammeMutation.isPending ||
                    !targetProgrammeId ||
                    universeQuery.isError
                  }
                  onClick={() => addToProgrammeMutation.mutate()}
                >
                  <CalendarPlus size={15} aria-hidden />{" "}
                  {addToProgrammeMutation.isPending
                    ? "Adding…"
                    : "Add annual schedule"}
                </button>
              ) : (
                <button
                  type="button"
                  className="is-primary"
                  onClick={() => {
                    setProgrammePrompt(null);
                    navigate(`/maintenance/${amoCode}/quality/audits/program`);
                  }}
                >
                  Open audit programme
                </button>
              )}
            </footer>
          </section>
        </div>
      ) : null}
      {deleteTarget ? (
        <div
          className="qa-audit-delete-modal"
          role="presentation"
          onMouseDown={() => !deleteMutation.isPending && setDeleteTarget(null)}
        >
          <section
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="qa-audit-delete-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <AlertTriangle size={20} aria-hidden />
                <h2 id="qa-audit-delete-title">Move audit to recycle bin?</h2>
              </div>
              <button
                type="button"
                aria-label="Close"
                disabled={deleteMutation.isPending}
                onClick={() => setDeleteTarget(null)}
              >
                <X size={18} />
              </button>
            </header>
            <p>
              <strong>
                {deleteTarget.audit_ref} · {deleteTarget.title}
              </strong>{" "}
              will leave active Assurance views. Its workflow, findings,
              corrective actions, checklists, evidence, notices, and files
              remain intact for restoration.
            </p>
            <label className="qa-audit-delete-modal__reason">
              Reason <span>Optional</span>
              <textarea
                value={deleteReason}
                maxLength={1000}
                placeholder="Add context for other Quality team members"
                onChange={(event) => setDeleteReason(event.target.value)}
              />
            </label>
            {deleteError ? (
              <p className="qa-audit-delete-modal__error" role="alert">
                {deleteError}
              </p>
            ) : null}
            <div className="qa-audit-delete-modal__notice">
              Recoverable for 30 days. Permanent deletion is available only in
              the Recycle Bin.
            </div>
            <footer>
              <button
                type="button"
                disabled={deleteMutation.isPending}
                onClick={() => setDeleteTarget(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="is-danger"
                disabled={deleteMutation.isPending}
                onClick={() =>
                  deleteMutation.mutate({
                    auditId: deleteTarget.id,
                    reason: deleteReason,
                  })
                }
              >
                <Trash2 size={15} />{" "}
                {deleteMutation.isPending ? "Moving…" : "Move to recycle bin"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditsWorkspacePage;
