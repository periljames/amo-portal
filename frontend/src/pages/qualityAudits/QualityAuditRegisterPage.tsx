import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ClipboardList, ShieldAlert, TableProperties } from "lucide-react";
import { hasQmsRolePermission } from "../../app/routeGuards";
import SpreadsheetToolbar from "../../components/shared/SpreadsheetToolbar";
import { ResponsiveSegmentedControl } from "../../components/QMS/ResponsiveSegmentedControl";
import { useDensityPreference } from "../../hooks/useDensityPreference";
import { getContext } from "../../services/auth";
import { qmsGetAuditRegisterPage } from "../../services/qmsRegisters";
import type { CAROut, QMSAuditOut, QMSFindingOut } from "../../services/qms";
import { auditNavigationHref } from "./auditNavigation";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import {
  FINDING_LIFECYCLE_OPTIONS,
  findingLifecycleLabel,
  findingLifecycleView,
  findingNextAction,
  parseFindingLifecycleView,
  primaryLinkedCar,
  toRegisterWorkflowStage,
  type FindingLifecycleView,
} from "./findingLifecycle";

type RegisterTab = "findings" | "cars";
type RegisterPageSize = 25 | 50 | 100;

type RegisterRow = {
  audit: QMSAuditOut;
  finding: QMSFindingOut;
  linkedCars: CAROut[];
};

type HeaderFilters = {
  ref: string;
  finding: string;
  audit: string;
  type: string;
  owner: string;
  car: string;
};

type PaginationState = {
  scopeKey: string;
  page: number;
};

const EMPTY_FILTERS: HeaderFilters = {
  ref: "",
  finding: "",
  audit: "",
  type: "",
  owner: "",
  car: "",
};

const QualityAuditRegisterPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab");
  const tab: RegisterTab = rawTab === "cars" ? "cars" : "findings";
  const stage = parseFindingLifecycleView(searchParams.get("stage"));
  const workflowStage = toRegisterWorkflowStage(stage);
  const auditId = searchParams.get("auditId")?.trim() || "";
  const [wrapText, setWrapText] = useState(false);
  const [showFilters, setShowFilters] = useState(true);
  const [showOwner, setShowOwner] = useState(true);
  const [quickFilter, setQuickFilter] = useState("");
  const [headerFilters, setHeaderFilters] = useState<HeaderFilters>(EMPTY_FILTERS);
  const [debouncedQuickFilter, setDebouncedQuickFilter] = useState("");
  const [debouncedHeaderFilters, setDebouncedHeaderFilters] = useState<HeaderFilters>(EMPTY_FILTERS);
  const [pageSize, setPageSize] = useState<RegisterPageSize>(25);
  const [pagination, setPagination] = useState<PaginationState>({ scopeKey: "", page: 1 });
  const { density, setDensity } = useDensityPreference("audit-register", "compact");

  const params = useParams<{ amoCode?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const navigate = useNavigate();
  const canCreateCar = hasQmsRolePermission("qms.car.create");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuickFilter(quickFilter.trim());
      setDebouncedHeaderFilters({
        ref: headerFilters.ref.trim(),
        finding: headerFilters.finding.trim(),
        audit: headerFilters.audit.trim(),
        type: headerFilters.type.trim(),
        owner: headerFilters.owner.trim(),
        car: headerFilters.car.trim(),
      });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [headerFilters, quickFilter]);

  const paginationScopeKey = useMemo(() => JSON.stringify([
    tab,
    stage,
    auditId,
    debouncedQuickFilter,
    debouncedHeaderFilters.ref,
    debouncedHeaderFilters.finding,
    debouncedHeaderFilters.audit,
    debouncedHeaderFilters.type,
    debouncedHeaderFilters.owner,
    debouncedHeaderFilters.car,
    pageSize,
  ]), [auditId, debouncedHeaderFilters, debouncedQuickFilter, pageSize, stage, tab]);
  const currentPage = pagination.scopeKey === paginationScopeKey ? pagination.page : 1;
  const setCurrentPage = (nextPage: number | ((page: number) => number)) => {
    setPagination((current) => {
      const basePage = current.scopeKey === paginationScopeKey ? current.page : 1;
      const page = typeof nextPage === "function" ? nextPage(basePage) : nextPage;
      return { scopeKey: paginationScopeKey, page };
    });
  };

  const registerQuery = useQuery({
    queryKey: [
      "qms-audit-register-paged",
      amoCode,
      tab,
      stage,
      auditId,
      debouncedQuickFilter,
      debouncedHeaderFilters,
      pageSize,
      currentPage,
    ],
    queryFn: ({ signal }) => qmsGetAuditRegisterPage({
      domain: "AMO",
      auditId: auditId || undefined,
      onlyWithCars: tab === "cars",
      workflowStage: tab === "findings" ? workflowStage : undefined,
      search: debouncedQuickFilter || undefined,
      ref: debouncedHeaderFilters.ref || undefined,
      finding: debouncedHeaderFilters.finding || undefined,
      audit: debouncedHeaderFilters.audit || undefined,
      findingType: debouncedHeaderFilters.type || undefined,
      owner: debouncedHeaderFilters.owner || undefined,
      car: debouncedHeaderFilters.car || undefined,
      limit: pageSize,
      offset: (currentPage - 1) * pageSize,
      signal,
    }),
    staleTime: 30_000,
    placeholderData: (previous) => previous,
  });

  const rows = useMemo<RegisterRow[]>(() => {
    return (registerQuery.data?.rows ?? []).map((row) => ({
      audit: row.audit,
      finding: row.finding,
      linkedCars: row.linked_cars,
    }));
  }, [registerQuery.data]);

  const total = registerQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const pageStart = total === 0 ? 0 : (safeCurrentPage - 1) * pageSize + 1;
  const pageEnd = total === 0 ? 0 : Math.min(total, (safeCurrentPage - 1) * pageSize + rows.length);

  const loading = registerQuery.isLoading;
  const refreshing = registerQuery.isFetching && !registerQuery.isLoading;
  const cellTextClass = wrapText ? "qms-cell-text qms-cell-text--wrap" : "qms-cell-text qms-cell-text--truncate";
  const filtersActive = Boolean(
    quickFilter.trim()
      || Object.values(headerFilters).some((value) => value.trim())
      || auditId
      || tab === "cars",
  );

  const clearFilters = () => {
    setQuickFilter("");
    setHeaderFilters(EMPTY_FILTERS);
    setCurrentPage(1);
  };

  return (
    <QualityAuditsSectionLayout
      title="Findings & Actions"
      subtitle="One operational queue for findings, linked corrective actions, deadlines and the next governed step."
      toolbar={
        <div className="audit-workspace__view-controls">
          <ResponsiveSegmentedControl
            label="Register dataset"
            value={tab}
            onChange={(nextTab: RegisterTab) => {
              const next = new URLSearchParams(searchParams);
              next.set("tab", nextTab);
              if (nextTab !== "findings") next.delete("stage");
              if (auditId) next.set("auditId", auditId);
              setSearchParams(next);
            }}
            compactIconsOnMobile
            options={[
              { value: "findings", label: "Findings", icon: ClipboardList },
              { value: "cars", label: "CARs", icon: ShieldAlert },
            ]}
          />
          {tab === "findings" ? (
            <ResponsiveSegmentedControl
              label="Finding lifecycle view"
              value={stage}
              onChange={(nextStage: FindingLifecycleView) => {
                const next = new URLSearchParams(searchParams);
                next.set("tab", "findings");
                if (nextStage === "all") next.delete("stage");
                else next.set("stage", nextStage);
                if (auditId) next.set("auditId", auditId);
                setSearchParams(next);
              }}
              options={FINDING_LIFECYCLE_OPTIONS.map((option) => ({ ...option, icon: TableProperties }))}
            />
          ) : null}
        </div>
      }
    >
      <div className="audit-workspace audit-workspace--register-dense">
        <div className="audit-workspace__toolbar-row">
          <label className="audit-search" aria-label="Quick filter register rows">
            <TableProperties size={15} />
            <input
              value={quickFilter}
              onChange={(event) => setQuickFilter(event.target.value)}
              placeholder="Filter audit ref, finding, owner, CAR…"
            />
          </label>
          <SpreadsheetToolbar
            density={density}
            onDensityChange={setDensity}
            wrapText={wrapText}
            onWrapTextChange={setWrapText}
            showFilters={showFilters}
            onShowFiltersChange={setShowFilters}
            columnToggles={[
              { id: "owner", label: "Owner", checked: showOwner, onToggle: () => setShowOwner((current) => !current) },
            ]}
          />
        </div>

        <div className="audit-panel">
          <div className="audit-panel__header audit-panel__header--dense">
            <div>
              <h2 className="audit-panel__title">
                {tab === "findings" ? findingLifecycleLabel(stage) : "CAR-linked findings"}
              </h2>
              <p className="audit-panel__subtitle">
                {pageStart}-{pageEnd} of {total}
                {tab === "cars" ? " · CAR-linked" : ""}
                {tab === "findings" && stage === "all" ? " · finding + CAR lifecycle" : ""}
                {refreshing ? " · refreshing" : ""}
              </p>
            </div>
            <div className="audit-chip-list audit-chip-list--dense">
              {filtersActive ? (
                <button type="button" className="secondary-chip-btn" onClick={clearFilters}>Clear</button>
              ) : null}
              <label className="qms-pill">
                Rows
                <select
                  value={pageSize}
                  onChange={(event) => setPageSize(Number(event.target.value) as RegisterPageSize)}
                  aria-label="Audit register rows per page"
                >
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </label>
              <span className="qms-pill">{density === "compact" ? "Compact" : "Comfortable"}</span>
              <span className="qms-pill">{registerQuery.data?.car_linked_findings ?? 0} with CARs</span>
              <span className="qms-pill">{registerQuery.data?.open_car_count ?? 0} open CARs</span>
            </div>
          </div>

          {registerQuery.isError ? (
            <div className="card card--error" role="alert">
              <p>{registerQuery.error instanceof Error ? registerQuery.error.message : "Failed to load the audit register."}</p>
              <button type="button" className="secondary-chip-btn" onClick={() => void registerQuery.refetch()}>Retry</button>
            </div>
          ) : null}

          <div className="table-wrapper">
            <table className={`table ${density === "compact" ? "table-row--compact" : "table-row--comfortable"} ${wrapText ? "table--wrap" : ""}`}>
              <thead>
                <tr>
                  <th>Status / stage</th>
                  <th>Finding</th>
                  <th>Audit</th>
                  <th>Due</th>
                  <th>Lead</th>
                  <th>Type</th>
                  {showOwner ? <th>Owner</th> : null}
                  <th>CARs</th>
                  <th>Action</th>
                </tr>
                {showFilters ? (
                  <tr>
                    <th />
                    <th><input className="input" placeholder="Finding text" value={headerFilters.finding} onChange={(event) => setHeaderFilters((current) => ({ ...current, finding: event.target.value }))} /></th>
                    <th><input className="input" placeholder="Audit ref / title" value={headerFilters.audit} onChange={(event) => setHeaderFilters((current) => ({ ...current, audit: event.target.value }))} /></th>
                    <th />
                    <th />
                    <th><input className="input" placeholder="Type" value={headerFilters.type} onChange={(event) => setHeaderFilters((current) => ({ ...current, type: event.target.value }))} /></th>
                    {showOwner ? <th><input className="input" placeholder="Owner" value={headerFilters.owner} onChange={(event) => setHeaderFilters((current) => ({ ...current, owner: event.target.value }))} /></th> : null}
                    <th><input className="input" placeholder="CAR" value={headerFilters.car} onChange={(event) => setHeaderFilters((current) => ({ ...current, car: event.target.value }))} /></th>
                    <th />
                  </tr>
                ) : null}
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={showOwner ? 9 : 8}>Loading register…</td>
                  </tr>
                ) : rows.length === 0 ? (
                  <tr>
                    <td colSpan={showOwner ? 9 : 8}>
                      {tab === "findings" && stage === "needs_review"
                        ? "No findings in RCA/CAP. Findings raised in Live that auto-create an OPEN CAR appear under Awaiting response or All."
                        : "No register rows match the current filters."}
                    </td>
                  </tr>
                ) : (
                  rows.map(({ audit, finding, linkedCars }) => {
                    const lifecycleStage = findingLifecycleView(finding, linkedCars);
                    const primaryCar = primaryLinkedCar(linkedCars);
                    const findingOpen = lifecycleStage !== "closed";
                    const detailPath = `/maintenance/${amoCode}/quality/findings/${encodeURIComponent(finding.id)}/overview`;
                    return (
                      <tr key={finding.id}>
                        <td>
                          <span className={`qms-pill${findingOpen ? " qms-pill--warn" : ""}`}>
                            {findingLifecycleLabel(lifecycleStage)}
                          </span>
                          <div className={`text-muted ${cellTextClass}`}>
                            {primaryCar?.status.replaceAll("_", " ") || "No linked CAR"}
                          </div>
                        </td>
                        <td>
                          <button type="button" className="qa-register-record-link" onClick={() => navigate(detailPath)}>
                            {finding.finding_ref || finding.id.slice(0, 8)}
                          </button>
                          <div className={cellTextClass} title={finding.description || undefined}>{finding.description}</div>
                          {finding.level || finding.severity ? (
                            <div className={`text-muted ${cellTextClass}`}>{finding.level || finding.severity}</div>
                          ) : null}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="qa-register-record-link"
                            onClick={() => navigate(auditNavigationHref(amoCode, audit))}
                          >
                            {audit.audit_ref}
                          </button>
                          <div className={`text-muted ${cellTextClass}`} title={audit.title || undefined}>{audit.title}</div>
                          <div className={`text-muted ${cellTextClass}`}>{audit.kind?.replaceAll("_", " ")}</div>
                        </td>
                        <td>
                          <span>{finding.target_close_date || primaryCar?.target_closure_date || primaryCar?.due_date || "Not set"}</span>
                        </td>
                        <td>{audit.lead_auditor_name || "Unassigned"}</td>
                        <td><span className="qms-pill">{finding.finding_type}</span></td>
                        {showOwner ? <td>{finding.acknowledged_by_name || "Unassigned"}</td> : null}
                        <td>
                          <div className="audit-chip-list">
                            {linkedCars.length === 0 ? (
                              <span className="text-muted">0</span>
                            ) : (
                              linkedCars.map((car) => (
                                <button
                                  key={car.id}
                                  type="button"
                                  onClick={() => navigate(`/maintenance/${amoCode}/quality/cars?carId=${car.id}`)}
                                  className="secondary-chip-btn"
                                  title={`${car.car_number} · ${car.title}`}
                                >
                                  {car.car_number}
                                </button>
                              ))
                            )}
                          </div>
                        </td>
                        <td>
                          <div className="qa-register-primary-action">
                            <button
                              type="button"
                              onClick={() => navigate(primaryCar
                                ? `/maintenance/${amoCode}/quality/cars?carId=${encodeURIComponent(primaryCar.id)}`
                                : canCreateCar
                                  ? `/maintenance/${amoCode}/quality/cars/new?findingId=${encodeURIComponent(finding.id)}`
                                  : detailPath)}
                              className="secondary-chip-btn"
                            >
                              {primaryCar
                                ? "Continue corrective action"
                                : canCreateCar
                                  ? "Create corrective action"
                                  : "Review finding"}
                            </button>
                            <small>
                              {!primaryCar && !canCreateCar
                                ? "Review finding and request corrective-action assignment"
                                : findingNextAction(lifecycleStage, Boolean(primaryCar))}
                            </small>
                            <button
                              type="button"
                              onClick={() => navigate(auditNavigationHref(amoCode, audit))}
                              className="qa-register-audit-link"
                            >
                              Open audit
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="qms-car-pagination" aria-label="Audit register pagination">
            <button
              type="button"
              className="secondary-chip-btn"
              onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
              disabled={safeCurrentPage <= 1 || registerQuery.isFetching}
            >
              Previous
            </button>
            <span>Page {safeCurrentPage} of {totalPages}</span>
            <button
              type="button"
              className="secondary-chip-btn"
              onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
              disabled={!registerQuery.data?.has_more || registerQuery.isFetching}
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditRegisterPage;
