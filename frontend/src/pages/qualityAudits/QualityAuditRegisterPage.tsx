import Pagination from "../../components/shared/Pagination";
import WorkspaceLoading from "../../components/shared/WorkspaceLoading";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import RecordTable from "../../components/shared/RecordTable";
import {
  Eye,
  ClipboardCheck,
  ClipboardList,
  ExternalLink,
  Filter,
  Info,
  RefreshCw,
  Search,
  Settings,
  ShieldAlert,
} from "lucide-react";

import { hasQmsRolePermission } from "../../app/routeGuards";
import { getCachedUser, getContext } from "../../services/auth";
import { qmsGetAuditRegisterPage } from "../../services/qmsRegisters";
import {
  qmsGetWorkflowSettings,
  qmsUpdateWorkflowSettings,
  type CAROut,
  type QMSAuditOut,
  type QMSFindingOut,
  type QualityWorkflowSettingsOut,
} from "../../services/qms";
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
import { caseDate } from "./carCaseModel";

type RegisterPageSize = 25 | 50 | 100;

type RegisterRow = {
  id: string;
  audit: QMSAuditOut;
  finding: QMSFindingOut;
  linkedCars: CAROut[];
  lifecycle: FindingLifecycleView;
  primaryCar: CAROut | null;
};

type FollowUpDraft = {
  reminderPercentages: string;
  finalReminderDays: string;
};

const FINDINGS_INFO =
  "Observations stay as findings. Nonconformities continue in the same row through auditee response, implementation, effectiveness review and closure.";

function humanize(value: unknown): string {
  return String(value || "").replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isObservation(finding: QMSFindingOut): boolean {
  return String(finding.finding_type || "").toUpperCase() === "OBSERVATION"
    || String(finding.level || "").toUpperCase().includes("LEVEL_4");
}

function canEditWorkflowSettings(): boolean {
  const user = getCachedUser();
  return Boolean(user?.is_superuser || user?.is_amo_admin || user?.role === "QUALITY_MANAGER");
}

function draftFromSettings(settings: QualityWorkflowSettingsOut): FollowUpDraft {
  return {
    reminderPercentages: (settings.car_reminder_percentages || []).join(", "),
    finalReminderDays: String(settings.final_reminder_days_before_due ?? 0),
  };
}

function parseReminderPercentages(value: string): number[] | null {
  const parts = value.split(/[,\s]+/).map((part) => part.trim()).filter(Boolean);
  if (!parts.length) return null;
  const numbers = parts.map((part) => Number(part));
  if (numbers.some((n) => !Number.isInteger(n) || n <= 0 || n >= 100)) return null;
  return Array.from(new Set(numbers)).sort((a, b) => b - a);
}

const QualityAuditRegisterPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const context = getContext();
  const amoCode = params.amoCode ?? context.amoCode ?? "UNKNOWN";
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = parseQmsRegisterFilters(searchParams);
  const { view: actorView, period, status: findingStatus, stage, timing, auditId, q: search, pageSize, page, level } = filters;
  const searchInputRef = useRef<HTMLInputElement>(null);
  const infoRef = useRef<HTMLDetailsElement>(null);
  const settingsRef = useRef<HTMLDetailsElement>(null);
  const filterRailRef = useRef<HTMLDivElement>(null);
  const canManageFollowUp = canEditWorkflowSettings();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [followUpDraft, setFollowUpDraft] = useState<FollowUpDraft>({ reminderPercentages: "75, 50, 25", finalReminderDays: "3" });
  const [followUpError, setFollowUpError] = useState("");
  const [followUpSaved, setFollowUpSaved] = useState(false);

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
      amoCode,
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

  const workflowQuery = useQuery({
    queryKey: ["qms-workflow-settings", amoCode],
    queryFn: () => qmsGetWorkflowSettings(),
    staleTime: 60_000,
  });

  /* The editable follow-up draft mirrors the latest governed workflow settings. */
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (workflowQuery.data) setFollowUpDraft(draftFromSettings(workflowQuery.data));
  }, [workflowQuery.data]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const saveFollowUp = useMutation({
    mutationFn: async () => {
      const percentages = parseReminderPercentages(followUpDraft.reminderPercentages);
      if (!percentages) throw new Error("Enter reminder milestones as whole percentages between 1 and 99 (for example 75, 50, 25).");
      const days = Number(followUpDraft.finalReminderDays);
      if (!Number.isInteger(days) || days < 0 || days > 30) throw new Error("Final reminder must be 0–30 days before due.");
      return qmsUpdateWorkflowSettings({
        car_reminder_percentages: percentages,
        final_reminder_days_before_due: days,
      });
    },
    onSuccess: (saved) => {
      setFollowUpError("");
      setFollowUpSaved(true);
      setFollowUpDraft(draftFromSettings(saved));
      void queryClient.setQueryData(["qms-workflow-settings", amoCode], saved);
      window.setTimeout(() => setFollowUpSaved(false), 1800);
    },
    onError: (error) => {
      setFollowUpSaved(false);
      setFollowUpError(error instanceof Error ? error.message : "Unable to save follow-up settings.");
    },
  });

  useEffect(() => {
    const closeChrome = (event: MouseEvent) => {
      const target = event.target as Node;
      if (infoRef.current && !infoRef.current.contains(target)) infoRef.current.open = false;
      if (settingsRef.current && !settingsRef.current.contains(target)) settingsRef.current.open = false;
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFiltersOpen(false);
    };
    document.addEventListener("mousedown", closeChrome);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", closeChrome);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

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
      minWidth: 150,
      valueGetter: ({ data }) => data ? (isObservation(data.finding) ? "Observation" : `${humanize(data.finding.level)} · ${humanize(data.finding.severity)}`) : "",
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
          <strong>{data.primaryCar?.responsible_personnel || (isObservation(data.finding) ? "Audit team" : "Unassigned")}</strong>
          <span>{caseDate(data.primaryCar?.target_closure_date || data.primaryCar?.due_date || data.finding.target_close_date)}</span>
        </div>
      ) : null,
    },
    {
      headerName: "Stage",
      flex: 0.85,
      minWidth: 135,
      cellRenderer: ({ data }: ICellRendererParams<RegisterRow>) => data ? (
        <div className="qa-register-grid__stack">
          <span title={findingNextAction(data.lifecycle, Boolean(data.primaryCar))} className={`qa-register-grid__status qa-register-grid__status--${data.lifecycle}`}>{findingLifecycleLabel(data.lifecycle)}</span>

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
          <button type="button" title="Open finding" aria-label="Open finding" onClick={() => openFinding(data)}><Eye size={15} /></button>
          {data.primaryCar || !isObservation(data.finding) ? <button type="button" title={data.primaryCar ? "Open corrective action" : "Continue finding"} aria-label={data.primaryCar ? "Open corrective action" : "Continue finding"} onClick={() => openCorrectiveAction(data)}>
            {data.primaryCar ? <ShieldAlert size={15} /> : <ExternalLink size={15} />}
          </button> : null}
        </div>
      ) : null,
    },
  ], [amoCode, navigate, openCorrectiveAction, openFinding]);


  const total = registerQuery.data?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  useEffect(() => {
    if (registerQuery.data && page > totalPages) patchFilters({ page: totalPages }, true);
  }, [page, totalPages, registerQuery.data, patchFilters]);
  const hasFilters = Boolean(auditId || search || stage !== "all" || timing || findingStatus || level || period || actorView === "mine");
  const hasFacetFilters = Boolean(auditId || stage !== "all" || timing || findingStatus || level || period || actorView === "mine");
  const updateFilter = (key: string, value: string) => patchFilters({ [key]: value, page: null });
  const clearFilters = () => patchFilters({ q: null, stage: null, timing: null, auditId: null, status: null, level: null, period: null, view: null, page: null });
  const auditsHref = withQmsQuery(qmsModulePath(amoCode, "audits", "workspace"), buildPreservedQmsQuery(searchParams));
  const settings = workflowQuery.data;

  return (
    <QualityAuditsSectionLayout
      title="Findings Register"
      subtitle="Register of findings and linked corrective actions."
    >
      <section className="qa-register-grid-page" aria-label="Findings register">
        <header className="qa-register-grid-page__toolbar">
          <div className="qa-register-grid-page__primary">
            <form
              className="qa-audits-list__search qa-register-grid-page__search"
              onSubmit={(event) => {
                event.preventDefault();
                updateFilter("q", searchInputRef.current?.value.trim() ?? "");
              }}
            >
              <input
                key={search}
                ref={searchInputRef}
                aria-label="Search finding, audit, owner or CAR"
                defaultValue={search}
                placeholder="Search finding, audit, owner or CAR"
                maxLength={160}
              />
              <button type="submit" className="qa-register-grid-page__icon-btn" title="Search" aria-label="Search">
                <Search size={15} aria-hidden />
              </button>
            </form>

            <div className="qa-register-grid-page__tools">
              <details
                ref={infoRef}
                className="qa-register-grid-page__popover"
                onToggle={(event) => {
                  if ((event.currentTarget as HTMLDetailsElement).open) {
                    if (settingsRef.current) settingsRef.current.open = false;
                    setFiltersOpen(false);
                  }
                }}
              >
                <summary className="qa-register-grid-page__icon-btn" title="About this register" aria-label="About this register">
                  <Info size={15} aria-hidden />
                </summary>
                <div className="qa-register-grid-page__popover-panel" role="note">
                  <strong>Findings register</strong>
                  <p>{FINDINGS_INFO}</p>
                </div>
              </details>

              <button
                type="button"
                className={`qa-register-grid-page__icon-btn qa-register-grid-page__filter-toggle${filtersOpen ? " is-active" : ""}`}
                title={filtersOpen ? "Hide filters" : "Show filters"}
                aria-label={filtersOpen ? "Hide filters" : "Show filters"}
                aria-expanded={filtersOpen}
                aria-controls="qa-register-filter-pan"
                onClick={() => {
                  if (infoRef.current) infoRef.current.open = false;
                  if (settingsRef.current) settingsRef.current.open = false;
                  setFiltersOpen((open) => !open);
                }}
              >
                <Filter size={15} aria-hidden />
                {hasFacetFilters ? <span className="qa-register-grid-page__filter-dot" aria-hidden /> : null}
              </button>

              <details
                ref={settingsRef}
                className="qa-register-grid-page__popover"
                onToggle={(event) => {
                  if ((event.currentTarget as HTMLDetailsElement).open) {
                    if (infoRef.current) infoRef.current.open = false;
                    setFiltersOpen(false);
                    setFollowUpError("");
                    setFollowUpSaved(false);
                    if (workflowQuery.data) setFollowUpDraft(draftFromSettings(workflowQuery.data));
                    else void workflowQuery.refetch();
                  }
                }}
              >
                <summary className="qa-register-grid-page__icon-btn" title="Follow-up settings" aria-label="Follow-up settings">
                  <Settings size={15} aria-hidden />
                </summary>
                <div className="qa-register-grid-page__popover-panel qa-register-grid-page__popover-panel--settings" role="dialog" aria-label="Follow-up settings">
                  <strong>Reminders &amp; escalation</strong>
                  <p>The system reminds owners automatically and escalates overdue corrective actions. Set the timing here.</p>
                  {workflowQuery.isLoading ? (
                    <span className="qa-register-grid-page__refreshing"><RefreshCw size={13} aria-hidden /> Loading settings…</span>
                  ) : workflowQuery.isError ? (
                    <p className="qa-register-grid-page__popover-error">{workflowQuery.error instanceof Error ? workflowQuery.error.message : "Settings unavailable."}</p>
                  ) : (
                    <>
                      <label>
                        Reminder milestones
                        <input
                          value={followUpDraft.reminderPercentages}
                          disabled={!canManageFollowUp || saveFollowUp.isPending}
                          onChange={(event) => setFollowUpDraft((current) => ({ ...current, reminderPercentages: event.target.value }))}
                          placeholder="75, 50, 25"
                          aria-describedby="qa-register-reminder-help"
                        />
                      </label>
                      <small id="qa-register-reminder-help">Percent of CAPA time remaining when reminders fire (for example 75, 50, 25).</small>
                      <label>
                        Final reminder (days before due)
                        <input
                          type="number"
                          min={0}
                          max={30}
                          value={followUpDraft.finalReminderDays}
                          disabled={!canManageFollowUp || saveFollowUp.isPending}
                          onChange={(event) => setFollowUpDraft((current) => ({ ...current, finalReminderDays: event.target.value }))}
                        />
                      </label>
                      <div className="qa-register-grid-page__escalation">
                        <span>Auto-escalation</span>
                        <strong>{settings?.auto_escalation_enabled ? "On" : "Off"}</strong>
                        <small>{settings?.auto_escalation_locked ? "Locked for this tenant — overdue actions escalate automatically." : "Overdue actions escalate after the final reminder window."}</small>
                      </div>
                      {followUpError ? <p className="qa-register-grid-page__popover-error">{followUpError}</p> : null}
                      {followUpSaved ? <p className="qa-register-grid-page__popover-ok">Saved.</p> : null}
                      {canManageFollowUp ? (
                        <button
                          type="button"
                          className="qa-register-grid-page__save"
                          disabled={saveFollowUp.isPending}
                          onClick={() => saveFollowUp.mutate()}
                        >
                          {saveFollowUp.isPending ? "Saving…" : "Save timing"}
                        </button>
                      ) : (
                        <small>Only Quality Managers can change these limits.</small>
                      )}
                    </>
                  )}
                </div>
              </details>
            </div>

            <div className="qa-register-grid-page__summary">
              {registerQuery.isFetching && !registerQuery.isLoading ? <span className="qa-register-grid-page__refreshing"><RefreshCw size={13} aria-hidden /> Updating</span> : null}
              {hasFilters ? <button type="button" onClick={clearFilters}>Clear filters</button> : null}
              {hasQmsRolePermission("qms.reports.view") ? (
                <button
                  type="button"
                  onClick={() => navigate(qmsModulePath(amoCode, "reports", "car-performance"))}
                  title="Analyse findings and corrective-action performance"
                >
                  Analysis
                </button>
              ) : null}
            </div>
          </div>

          <div
            ref={filterRailRef}
            className={`qa-register-grid-page__filter-rail${filtersOpen ? " is-open" : ""}${hasFacetFilters ? " has-active" : ""}`}
          >
            <div
              id="qa-register-filter-pan"
              className="qa-register-grid-page__filter-pan"
              aria-hidden={!filtersOpen}
            >
              <div className="qa-register-grid-page__filter-pan-inner">
                <label>Scope<select aria-label="Scope" value={actorView} onChange={(event) => updateFilter("view", event.target.value)} tabIndex={filtersOpen ? 0 : -1}><option value="global">Global</option><option value="mine">My Work</option></select></label>
                <label>Year<input aria-label="Year" type="number" min={2000} max={2200} value={period ?? ""} placeholder="All years" onChange={(event) => updateFilter("period", event.target.value)} tabIndex={filtersOpen ? 0 : -1} /></label>
                <label>Status<select aria-label="Status" value={findingStatus} onChange={(event) => updateFilter("status", event.target.value)} tabIndex={filtersOpen ? 0 : -1}><option value="">All</option><option value="open">Open</option><option value="closed">Closed</option></select></label>
                <label>Level<select aria-label="Level" value={level} onChange={(event) => updateFilter("level", event.target.value)} tabIndex={filtersOpen ? 0 : -1}><option value="">All</option>{[1, 2, 3, 4].map((number) => <option key={number} value={`LEVEL_${number}`}>Level {number}</option>)}</select></label>
                <label>Stage<select aria-label="Stage" value={stage} onChange={(event) => updateFilter("stage", event.target.value)} tabIndex={filtersOpen ? 0 : -1}>
                    {FINDING_LIFECYCLE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
                <label>Due position<select aria-label="Due position" value={timing} onChange={(event) => updateFilter("timing", event.target.value)} tabIndex={filtersOpen ? 0 : -1}>
                    <option value="">All due dates</option><option value="overdue">Overdue</option><option value="due_soon">Due in 30 days</option>
                  </select>
                </label>
              </div>
            </div>
          </div>
        </header>

        {registerQuery.isLoading ? (
          <WorkspaceLoading label="Loading findings" compact />
        ) : registerQuery.isError ? (
          <div className="qa-audits-list__state qa-audits-list__state--error" role="alert">
            <strong>Register unavailable.</strong><span>{registerQuery.error instanceof Error ? registerQuery.error.message : "Try again."}</span>
            <button type="button" onClick={() => void registerQuery.refetch()}>Retry</button>
          </div>
        ) : rows.length ? (
          <>
            <div className="qa-register-mobile-list" aria-label="Findings">
              {rows.map(row => <article key={row.id} className="qa-register-mobile-card">
                <header><button type="button" onClick={() => openFinding(row)}>{row.finding.finding_ref || "Finding"}</button><span className={`qa-register-grid__status qa-register-grid__status--${row.lifecycle}`}>{findingLifecycleLabel(row.lifecycle)}</span></header>
                <p>{row.finding.description}</p>
                <dl><div><dt>Audit</dt><dd>{row.audit.audit_ref}</dd></div><div><dt>Classification</dt><dd>{isObservation(row.finding) ? "Observation" : humanize(row.finding.level || row.finding.severity)}</dd></div><div><dt>Owner</dt><dd>{row.primaryCar?.responsible_personnel || (isObservation(row.finding) ? "Audit team" : "Unassigned")}</dd></div><div><dt>Due</dt><dd>{caseDate(row.primaryCar?.target_closure_date || row.primaryCar?.due_date || row.finding.target_close_date)}</dd></div></dl>
                <footer><button type="button" onClick={() => openFinding(row)}>Open finding</button>{row.primaryCar ? <button type="button" onClick={() => openCorrectiveAction(row)}>{row.primaryCar.car_number}</button> : null}</footer>
              </article>)}
            </div>
            <div className="qa-register-grid-page__grid" style={{ "--finding-row-count": rows.length } as React.CSSProperties} aria-busy={registerQuery.isFetching}>
              <RecordTable rows={rows} columns={columnDefs} label="Findings" onRowDoubleClick={(data) => openFinding(data)} />
            </div>

            <Pagination label="Findings" page={page} pageSize={pageSize} total={registerQuery.data ? total : undefined} visibleCount={rows.length} busy={registerQuery.isFetching} onPageChange={(value)=>patchFilters({page:value})} onPageSizeChange={(value)=>patchFilters({pageSize:value as RegisterPageSize,page:null})} />
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
