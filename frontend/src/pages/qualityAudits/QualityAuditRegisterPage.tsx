import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ClipboardList, ShieldAlert, TableProperties } from "lucide-react";
import SpreadsheetToolbar from "../../components/shared/SpreadsheetToolbar";
import { ResponsiveSegmentedControl } from "../../components/QMS/ResponsiveSegmentedControl";
import { useDensityPreference } from "../../hooks/useDensityPreference";
import { getContext } from "../../services/auth";
import { qmsGetAuditRegisterPage } from "../../services/qmsRegisters";
import type { CAROut, QMSAuditOut, QMSFindingOut } from "../../services/qms";
import { buildAuditWorkspacePath } from "../../utils/auditSlug";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";

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

  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const navigate = useNavigate();

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
    auditId,
    debouncedQuickFilter,
    debouncedHeaderFilters.ref,
    debouncedHeaderFilters.finding,
    debouncedHeaderFilters.audit,
    debouncedHeaderFilters.type,
    debouncedHeaderFilters.owner,
    debouncedHeaderFilters.car,
    pageSize,
  ]), [auditId, debouncedHeaderFilters, debouncedQuickFilter, pageSize, tab]);
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
      title="Register"
      subtitle="Operational closeout register for findings and linked CAR actions."
      toolbar={
        <ResponsiveSegmentedControl
          label="Register dataset"
          value={tab}
          onChange={(nextTab: RegisterTab) => {
            const next = new URLSearchParams(searchParams);
            next.set("tab", nextTab);
            if (auditId) next.set("auditId", auditId);
            setSearchParams(next);
          }}
          compactIconsOnMobile
          options={[
            { value: "findings", label: "Findings", icon: ClipboardList },
            { value: "cars", label: "CARs", icon: ShieldAlert },
          ]}
        />
      }
    >
      <div className="audit-workspace">
        <div className="audit-workspace__toolbar-row">
          <label className="audit-search" aria-label="Quick filter register rows">
            <TableProperties size={15} />
            <input
              value={quickFilter}
              onChange={(event) => setQuickFilter(event.target.value)}
              placeholder="Quick filter across audit ref, finding, owner, CAR, and summary"
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
          <div className="audit-panel__header">
            <div>
              <h2 className="audit-panel__title">Closeout register</h2>
              <p className="audit-panel__subtitle">
                {pageStart}-{pageEnd} of {total} matched rows · {tab === "cars" ? "CAR-linked findings only" : "all findings"}
                {refreshing ? " · refreshing" : ""}
              </p>
            </div>
            <div className="audit-chip-list">
              {filtersActive ? (
                <button type="button" className="secondary-chip-btn" onClick={clearFilters}>Clear filters</button>
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
              <span className="qms-pill">{density === "compact" ? "Compact density" : "Comfortable density"}</span>
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
                  <th>Finding ref</th>
                  <th>Audit ref</th>
                  <th>Finding</th>
                  <th>Type</th>
                  {showOwner ? <th>Owner</th> : null}
                  <th>Linked CARs</th>
                  <th>Action</th>
                </tr>
                {showFilters ? (
                  <tr>
                    <th><input className="input" placeholder="Find ref" value={headerFilters.ref} onChange={(event) => setHeaderFilters((current) => ({ ...current, ref: event.target.value }))} /></th>
                    <th><input className="input" placeholder="Audit ref / title" value={headerFilters.audit} onChange={(event) => setHeaderFilters((current) => ({ ...current, audit: event.target.value }))} /></th>
                    <th><input className="input" placeholder="Finding text" value={headerFilters.finding} onChange={(event) => setHeaderFilters((current) => ({ ...current, finding: event.target.value }))} /></th>
                    <th><input className="input" placeholder="Type" value={headerFilters.type} onChange={(event) => setHeaderFilters((current) => ({ ...current, type: event.target.value }))} /></th>
                    {showOwner ? <th><input className="input" placeholder="Owner" value={headerFilters.owner} onChange={(event) => setHeaderFilters((current) => ({ ...current, owner: event.target.value }))} /></th> : null}
                    <th><input className="input" placeholder="CAR number / title" value={headerFilters.car} onChange={(event) => setHeaderFilters((current) => ({ ...current, car: event.target.value }))} /></th>
                    <th />
                  </tr>
                ) : null}
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={showOwner ? 7 : 6}>Loading register…</td>
                  </tr>
                ) : rows.length === 0 ? (
                  <tr>
                    <td colSpan={showOwner ? 7 : 6}>No register rows match the current filters.</td>
                  </tr>
                ) : (
                  rows.map(({ audit, finding, linkedCars }) => (
                    <tr key={finding.id}>
                      <td>{finding.finding_ref || finding.id}</td>
                      <td>
                        <strong>{audit.audit_ref}</strong>
                        <div className={`text-muted ${cellTextClass}`}>{audit.title}</div>
                      </td>
                      <td>
                        <div className={cellTextClass}>{finding.description}</div>
                        <div className={`text-muted ${cellTextClass}`}>{finding.objective_evidence || "No objective evidence captured."}</div>
                      </td>
                      <td><span className="qms-pill">{finding.finding_type}</span></td>
                      {showOwner ? <td>{finding.acknowledged_by_name || "Unassigned"}</td> : null}
                      <td>
                        <div className="audit-chip-list">
                          {linkedCars.length === 0 ? <span className="text-muted">No linked CARs</span> : linkedCars.map((car) => (
                            <button
                              key={car.id}
                              type="button"
                              onClick={() => navigate(`/maintenance/${amoCode}/quality/cars?carId=${car.id}`)}
                              className="secondary-chip-btn"
                              title={`${car.car_number} · ${car.title}`}
                            >
                              {car.car_number}
                            </button>
                          ))}
                        </div>
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => navigate(buildAuditWorkspacePath({ amoCode, department, auditRef: audit.audit_ref }))}
                          className="secondary-chip-btn"
                        >
                          View audit
                        </button>
                      </td>
                    </tr>
                  ))
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

        <div className="audit-stats-grid">
          <div className="audit-stat-card">
            <div className="audit-stat-card__label"><ClipboardList size={15} /> Findings in scope</div>
            <div className="audit-stat-card__value">{total}</div>
          </div>
          <div className="audit-stat-card">
            <div className="audit-stat-card__label"><ShieldAlert size={15} /> Findings with CARs</div>
            <div className="audit-stat-card__value">{registerQuery.data?.car_linked_findings ?? 0}</div>
          </div>
          <div className="audit-stat-card">
            <div className="audit-stat-card__label"><AlertTriangle size={15} /> Open CAR count</div>
            <div className="audit-stat-card__value">{registerQuery.data?.open_car_count ?? 0}</div>
          </div>
        </div>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditRegisterPage;
