import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { hasQmsRolePermission } from "../../app/routeGuards";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getContext } from "../../services/auth";
import { type CAROut } from "../../services/qms";
import { qmsGetCarRegisterPage } from "../../services/qmsRegisters";
import { saveDownloadedFile } from "../../utils/downloads";

const PAGE_SIZE = 100;
const REPORT_ROW_CAP = 10_000;
const QMS_CLOSURE_TARGET = 80;

type ReportScope = "ALL" | "OPEN" | "OVERDUE" | "REVIEW" | "CLOSED";

type LoadedReport = {
  items: CAROut[];
  total: number;
  truncated: boolean;
};

type DepartmentMetric = {
  department: string;
  total: number;
  open: number;
  overdue: number;
  review: number;
  closed: number;
  measurableClosed: number;
  onTimeClosed: number;
};

function dateOnly(value: string | null | undefined): string | null {
  if (!value) return null;
  const clean = String(value).slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(clean) ? clean : null;
}

function formatDate(value: string | null | undefined): string {
  const clean = dateOnly(value);
  if (!clean) return "—";
  const parsed = new Date(`${clean}T00:00:00Z`);
  return Number.isNaN(parsed.getTime())
    ? clean
    : parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (character) => character.toUpperCase());
}

function agreedDue(car: CAROut): string | null {
  return dateOnly(car.target_closure_date) || dateOnly(car.due_date);
}

function closedDate(car: CAROut): string | null {
  return dateOnly(car.date_closed) || dateOnly(car.closed_at);
}

function issuedDate(car: CAROut): string | null {
  return dateOnly(car.date_issued) || dateOnly(car.created_at);
}

function isClosed(car: CAROut): boolean {
  return car.status === "CLOSED";
}

function isOpen(car: CAROut): boolean {
  return !["CLOSED", "CANCELLED"].includes(car.status);
}

function isInReview(car: CAROut): boolean {
  return car.status === "PENDING_VERIFICATION"
    || car.root_cause_status === "SUBMITTED"
    || car.capa_status === "SUBMITTED"
    || car.capa_status === "NEEDS_EVIDENCE";
}

function isOverdue(car: CAROut, today: string): boolean {
  const due = agreedDue(car);
  return Boolean(isOpen(car) && due && due < today);
}

function isMeasurableClosure(car: CAROut): boolean {
  return Boolean(isClosed(car) && agreedDue(car) && closedDate(car));
}

function isOnTimeClosure(car: CAROut): boolean {
  const due = agreedDue(car);
  const closed = closedDate(car);
  return Boolean(isClosed(car) && due && closed && closed <= due);
}

function ownerLabel(car: CAROut): string {
  return car.responsible_personnel || car.assigned_to_user_id || "Unassigned";
}

function departmentLabel(car: CAROut): string {
  return car.responsible_department?.trim() || "Unassigned";
}

function csvCell(value: unknown): string {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadAllCars(signal: AbortSignal): Promise<LoadedReport> {
  const items: CAROut[] = [];
  let offset = 0;
  let total = 0;

  while (items.length < REPORT_ROW_CAP) {
    const page = await qmsGetCarRegisterPage({
      scope: "all",
      limit: PAGE_SIZE,
      offset,
      signal,
    });
    total = page.total;
    items.push(...page.items);
    if (!page.has_more || page.items.length === 0 || items.length >= total) break;
    offset += page.limit || page.items.length;
  }

  return {
    items: items.slice(0, REPORT_ROW_CAP),
    total,
    truncated: total > REPORT_ROW_CAP,
  };
}

const QmsCarPerformanceReportPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const context = getContext();
  const navigate = useNavigate();
  const amoCode = params.amoCode || context.amoSlug || context.amoCode || "UNKNOWN";
  const canViewReports = hasQmsRolePermission("qms.reports.view");

  const [scope, setScope] = useState<ReportScope>("ALL");
  const [department, setDepartment] = useState("");
  const [priority, setPriority] = useState("");
  const [search, setSearch] = useState("");
  const [issuedFrom, setIssuedFrom] = useState("");
  const [issuedTo, setIssuedTo] = useState("");
  const [outputError, setOutputError] = useState<string | null>(null);

  const reportQuery = useQuery({
    queryKey: ["qms-car-performance-live", amoCode],
    queryFn: ({ signal }) => loadAllCars(signal),
    enabled: canViewReports,
    staleTime: 30_000,
  });

  const allCars = reportQuery.data?.items ?? [];
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const generatedAt = useMemo(
    () => new Date(reportQuery.dataUpdatedAt || Date.now()),
    [reportQuery.dataUpdatedAt],
  );

  const departments = useMemo(
    () => Array.from(new Set(allCars.map(departmentLabel))).sort((left, right) => left.localeCompare(right)),
    [allCars],
  );

  const filteredCars = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return allCars.filter((car) => {
      if (scope === "OPEN" && !isOpen(car)) return false;
      if (scope === "OVERDUE" && !isOverdue(car, today)) return false;
      if (scope === "REVIEW" && !isInReview(car)) return false;
      if (scope === "CLOSED" && !isClosed(car)) return false;
      if (department && departmentLabel(car) !== department) return false;
      if (priority && car.priority !== priority) return false;
      const issued = issuedDate(car);
      if (issuedFrom && (!issued || issued < issuedFrom)) return false;
      if (issuedTo && (!issued || issued > issuedTo)) return false;
      if (needle) {
        const haystack = [
          car.car_number,
          car.title,
          car.summary,
          car.audit_ref,
          car.audit_title,
          car.finding_ref,
          car.finding_description,
          car.responsible_department,
          car.responsible_personnel,
          car.auditor_name,
        ].filter(Boolean).join(" ").toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }, [allCars, department, issuedFrom, issuedTo, priority, scope, search, today]);

  const metrics = useMemo(() => {
    const total = filteredCars.length;
    const open = filteredCars.filter(isOpen).length;
    const overdue = filteredCars.filter((car) => isOverdue(car, today)).length;
    const review = filteredCars.filter(isInReview).length;
    const closed = filteredCars.filter(isClosed).length;
    const measurable = filteredCars.filter(isMeasurableClosure);
    const onTime = measurable.filter(isOnTimeClosure).length;
    const late = measurable.length - onTime;
    const onTimePercent = measurable.length ? (onTime / measurable.length) * 100 : null;
    return { total, open, overdue, review, closed, measurable: measurable.length, onTime, late, onTimePercent };
  }, [filteredCars, today]);

  const departmentMetrics = useMemo<DepartmentMetric[]>(() => {
    const grouped = new Map<string, DepartmentMetric>();
    filteredCars.forEach((car) => {
      const key = departmentLabel(car);
      const current = grouped.get(key) || {
        department: key,
        total: 0,
        open: 0,
        overdue: 0,
        review: 0,
        closed: 0,
        measurableClosed: 0,
        onTimeClosed: 0,
      };
      current.total += 1;
      if (isOpen(car)) current.open += 1;
      if (isOverdue(car, today)) current.overdue += 1;
      if (isInReview(car)) current.review += 1;
      if (isClosed(car)) current.closed += 1;
      if (isMeasurableClosure(car)) current.measurableClosed += 1;
      if (isOnTimeClosure(car)) current.onTimeClosed += 1;
      grouped.set(key, current);
    });
    return [...grouped.values()].sort((left, right) => right.overdue - left.overdue || right.open - left.open || left.department.localeCompare(right.department));
  }, [filteredCars, today]);

  const activeFilterLabel = useMemo(() => {
    const filters = [
      scope !== "ALL" ? `scope=${scope.toLowerCase()}` : "",
      department ? `department=${department}` : "",
      priority ? `priority=${priority.toLowerCase()}` : "",
      issuedFrom ? `issued from ${issuedFrom}` : "",
      issuedTo ? `issued to ${issuedTo}` : "",
      search.trim() ? `search=${search.trim()}` : "",
    ].filter(Boolean);
    return filters.length ? filters.join("; ") : "No filters — all CARs";
  }, [department, issuedFrom, issuedTo, priority, scope, search]);

  const exportCsv = () => {
    setOutputError(null);
    const header = [
      "CAR Reference", "Title", "Audit", "Finding", "Department", "Owner", "Priority", "Status",
      "Issued", "Agreed Due", "Closed", "Timeliness", "RCA Status", "CAP Status",
    ];
    const rows = filteredCars.map((car) => [
      car.car_number,
      car.title,
      car.audit_ref || car.audit_title || "",
      car.finding_ref || car.finding_description || "",
      departmentLabel(car),
      ownerLabel(car),
      car.priority,
      car.status,
      issuedDate(car) || "",
      agreedDue(car) || "",
      closedDate(car) || "",
      isMeasurableClosure(car) ? (isOnTimeClosure(car) ? "ON TIME" : "LATE") : isOverdue(car, today) ? "OVERDUE" : "",
      car.root_cause_status || "",
      car.capa_status || "",
    ]);
    const metadata = [
      ["Generated at", generatedAt.toISOString()],
      ["Active filters", activeFilterLabel],
      ["QMSM QPI 3 target", `${QMS_CLOSURE_TARGET}% closure within agreed timeframe`],
      ["Measured on-time closure", metrics.onTimePercent == null ? "N/A" : `${metrics.onTimePercent.toFixed(1)}%`],
      [],
    ];
    const csv = [
      ...metadata.map((row) => row.map(csvCell).join(",")),
      header.map(csvCell).join(","),
      ...rows.map((row) => row.map(csvCell).join(",")),
    ].join("\n");
    saveDownloadedFile(new Blob([csv], { type: "text/csv;charset=utf-8" }), `QMS-CAR-performance-${today}.csv`);
  };

  const printReport = () => {
    setOutputError(null);
    const popup = window.open("", "_blank", "width=1200,height=850");
    if (!popup) {
      setOutputError("The browser blocked the printable report window. Allow pop-ups for this portal and try again.");
      return;
    }
    popup.opener = null;
    const departmentRows = departmentMetrics.map((item) => {
      const percent = item.measurableClosed ? `${((item.onTimeClosed / item.measurableClosed) * 100).toFixed(1)}%` : "N/A";
      return `<tr><td>${escapeHtml(item.department)}</td><td>${item.total}</td><td>${item.open}</td><td>${item.overdue}</td><td>${item.review}</td><td>${item.closed}</td><td>${escapeHtml(percent)}</td></tr>`;
    }).join("");
    const carRows = filteredCars.map((car) => {
      const timeliness = isMeasurableClosure(car) ? (isOnTimeClosure(car) ? "On time" : "Late") : isOverdue(car, today) ? "Overdue" : "—";
      return `<tr><td>${escapeHtml(car.car_number)}</td><td>${escapeHtml(car.title)}</td><td>${escapeHtml(departmentLabel(car))}</td><td>${escapeHtml(ownerLabel(car))}</td><td>${escapeHtml(humanize(car.priority))}</td><td>${escapeHtml(humanize(car.status))}</td><td>${escapeHtml(formatDate(agreedDue(car)))}</td><td>${escapeHtml(formatDate(closedDate(car)))}</td><td>${escapeHtml(timeliness)}</td></tr>`;
    }).join("");
    const onTimeText = metrics.onTimePercent == null ? "N/A" : `${metrics.onTimePercent.toFixed(1)}%`;
    const targetPosition = metrics.onTimePercent == null ? "Insufficient measurable closures" : metrics.onTimePercent >= QMS_CLOSURE_TARGET ? "Target achieved" : "Below target";
    popup.document.open();
    popup.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>QMS CAR Performance</title><style>@page{size:A4 landscape;margin:12mm}body{font:11px Arial,sans-serif;color:#111}h1{font-size:20px;margin:0 0 3px}h2{font-size:14px;border-bottom:1px solid #333;padding-bottom:4px;margin-top:18px}.meta{margin:6px 0 14px;color:#444}.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}.kpi{border:1px solid #aaa;padding:7px}.kpi span{display:block;color:#555;font-size:9px;text-transform:uppercase}.kpi strong{font-size:16px}table{width:100%;border-collapse:collapse;margin-top:8px;font-size:9px}th,td{border:1px solid #aaa;padding:4px;vertical-align:top;text-align:left}th{background:#eee}.note{border:1px solid #aaa;padding:7px;margin:8px 0}.no-print{margin-bottom:8px}@media print{.no-print{display:none}}</style></head><body><button class="no-print" onclick="window.print()">Print / Save PDF</button><h1>QMS CAR Performance Report</h1><div class="meta">Generated ${escapeHtml(generatedAt.toLocaleString())}<br>Filters: ${escapeHtml(activeFilterLabel)}</div><div class="note"><strong>QMSM 2.5 — Quality Performance Indicator 3:</strong> 80% closure of findings within the agreed timeframe. This report measures closed CARs where both an agreed/current due date and a closure date are recorded.</div><div class="kpis"><div class="kpi"><span>Total</span><strong>${metrics.total}</strong></div><div class="kpi"><span>Open</span><strong>${metrics.open}</strong></div><div class="kpi"><span>Overdue</span><strong>${metrics.overdue}</strong></div><div class="kpi"><span>Quality review</span><strong>${metrics.review}</strong></div><div class="kpi"><span>Closed</span><strong>${metrics.closed}</strong></div><div class="kpi"><span>On-time closure</span><strong>${escapeHtml(onTimeText)}</strong><div>${escapeHtml(targetPosition)}</div></div></div><h2>Department performance</h2><table><thead><tr><th>Department</th><th>Total</th><th>Open</th><th>Overdue</th><th>Review</th><th>Closed</th><th>On-time %</th></tr></thead><tbody>${departmentRows || '<tr><td colspan="7">No matching CARs.</td></tr>'}</tbody></table><h2>CAR detail</h2><table><thead><tr><th>CAR</th><th>Title</th><th>Department</th><th>Owner</th><th>Priority</th><th>Status</th><th>Agreed due</th><th>Closed</th><th>Timeliness</th></tr></thead><tbody>${carRows || '<tr><td colspan="9">No matching CARs.</td></tr>'}</tbody></table>${reportQuery.data?.truncated ? `<div class="note"><strong>Data warning:</strong> the tenant contains more than ${REPORT_ROW_CAP.toLocaleString()} CARs. The printable detail is capped and should not be treated as a full historical extract.</div>` : ""}</body></html>`);
    popup.document.close();
  };

  if (!canViewReports) {
    return (
      <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
        <main className="page"><div className="card"><h1>CAR performance</h1><p>Reports & Analytics permission is required to view this workspace.</p></div></main>
      </DepartmentLayout>
    );
  }

  if (reportQuery.isLoading) {
    return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><main className="page"><div className="card">Loading live CAR performance…</div></main></DepartmentLayout>;
  }

  if (reportQuery.isError || !reportQuery.data) {
    return (
      <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
        <main className="page"><div className="card"><h1>CAR performance</h1><p className="text-danger">{reportQuery.error instanceof Error ? reportQuery.error.message : "Unable to load CAR performance."}</p><button className="btn" type="button" onClick={() => void reportQuery.refetch()}>Retry</button></div></main>
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <main className="page qms-car-performance-report">
        <div className="page-header">
          <div>
            <p className="eyebrow">Reports & Analytics · Management review input</p>
            <h1>CAR performance</h1>
            <p>Live corrective-action performance, closure timeliness, overdue exposure and department accountability.</p>
          </div>
          <div className="toolbar">
            <button className="btn" type="button" onClick={() => navigate(`/maintenance/${amoCode}/quality/cars/register`)}>CAR register</button>
            <button className="btn" type="button" onClick={() => void reportQuery.refetch()}>Refresh</button>
            <button className="btn" type="button" onClick={exportCsv}>Export CSV</button>
            <button className="btn btn--primary" type="button" onClick={printReport}>Print report</button>
          </div>
        </div>

        {outputError ? <div className="alert alert--danger" role="alert">{outputError}</div> : null}
        {reportQuery.data.truncated ? <div className="alert alert--warning">This tenant has more than {REPORT_ROW_CAP.toLocaleString()} CARs. The interactive report is capped at {REPORT_ROW_CAP.toLocaleString()} rows; use a server-side archival export for a complete historical extract.</div> : null}

        <section className="card">
          <div className="card__header"><div><h2>Reporting position</h2><p>Generated {generatedAt.toLocaleString()} · {activeFilterLabel}</p></div></div>
          <div className="form-grid">
            <label>Scope<select className="input" value={scope} onChange={(event) => setScope(event.target.value as ReportScope)}><option value="ALL">All CARs</option><option value="OPEN">Open / active</option><option value="OVERDUE">Overdue</option><option value="REVIEW">Awaiting Quality review</option><option value="CLOSED">Closed</option></select></label>
            <label>Responsible department<select className="input" value={department} onChange={(event) => setDepartment(event.target.value)}><option value="">All departments</option>{departments.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label>Priority<select className="input" value={priority} onChange={(event) => setPriority(event.target.value)}><option value="">All priorities</option><option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH">High</option><option value="CRITICAL">Critical</option></select></label>
            <label>Issued from<input className="input" type="date" value={issuedFrom} onChange={(event) => setIssuedFrom(event.target.value)} /></label>
            <label>Issued to<input className="input" type="date" value={issuedTo} onChange={(event) => setIssuedTo(event.target.value)} /></label>
            <label>Search<input className="input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="CAR, audit, finding, owner, department…" /></label>
          </div>
        </section>

        <section className="card">
          <div className="card__header"><div><h2>QPI and workload</h2><p>QMSM 2.5 QPI 3 target: at least {QMS_CLOSURE_TARGET}% of findings closed within the agreed timeframe.</p></div></div>
          <div className="stats-grid">
            <div><span className="muted">Matching CARs</span><strong>{metrics.total}</strong></div>
            <div><span className="muted">Open / active</span><strong>{metrics.open}</strong></div>
            <div><span className="muted">Overdue</span><strong>{metrics.overdue}</strong></div>
            <div><span className="muted">Awaiting Quality review</span><strong>{metrics.review}</strong></div>
            <div><span className="muted">Closed</span><strong>{metrics.closed}</strong></div>
            <div><span className="muted">On-time closure</span><strong>{metrics.onTimePercent == null ? "N/A" : `${metrics.onTimePercent.toFixed(1)}%`}</strong><div className="muted">{metrics.measurable} measurable · {metrics.onTime} on time · {metrics.late} late</div></div>
          </div>
          {metrics.onTimePercent != null ? <div className={`alert ${metrics.onTimePercent >= QMS_CLOSURE_TARGET ? "alert--success" : "alert--warning"}`}><strong>{metrics.onTimePercent >= QMS_CLOSURE_TARGET ? "QPI target achieved" : "QPI target below requirement"}</strong> · {metrics.onTimePercent.toFixed(1)}% against {QMS_CLOSURE_TARGET}% target for the current filters.</div> : <div className="alert">No measurable closed CARs are available under the current filters. A closure date and agreed/current due date are required for the QPI denominator.</div>}
        </section>

        <section className="card">
          <div className="card__header"><div><h2>Department performance</h2><p>Accountability view for management review and follow-up. Departments with overdue/open exposure are listed first.</p></div></div>
          <div className="table-wrap"><table className="table"><thead><tr><th>Department</th><th>Total</th><th>Open</th><th>Overdue</th><th>Review</th><th>Closed</th><th>On-time closure</th></tr></thead><tbody>{departmentMetrics.length ? departmentMetrics.map((item) => <tr key={item.department}><td><strong>{item.department}</strong></td><td>{item.total}</td><td>{item.open}</td><td>{item.overdue}</td><td>{item.review}</td><td>{item.closed}</td><td>{item.measurableClosed ? `${((item.onTimeClosed / item.measurableClosed) * 100).toFixed(1)}%` : "N/A"}</td></tr>) : <tr><td colSpan={7} className="muted">No CARs match the active filters.</td></tr>}</tbody></table></div>
        </section>

        <section className="card">
          <div className="card__header"><div><h2>CAR performance detail</h2><p>Current agreed due date is the approved target closure date when present; otherwise the original CAR due date is used.</p></div><span className="badge badge--neutral">{filteredCars.length} row{filteredCars.length === 1 ? "" : "s"}</span></div>
          <div className="table-wrap"><table className="table"><thead><tr><th>CAR / finding</th><th>Department / owner</th><th>Priority</th><th>Status</th><th>Issued</th><th>Agreed due</th><th>Closed</th><th>Timeliness</th><th>RCA / CAP</th><th /></tr></thead><tbody>{filteredCars.length ? filteredCars.map((car) => {
            const timeliness = isMeasurableClosure(car) ? (isOnTimeClosure(car) ? "On time" : "Late") : isOverdue(car, today) ? "Overdue" : "—";
            return <tr key={car.id}><td><strong>{car.car_number}</strong><div>{car.title}</div><div className="muted">{car.finding_ref || car.audit_ref || "No linked finding reference"}</div></td><td><strong>{departmentLabel(car)}</strong><div className="muted">{ownerLabel(car)}</div></td><td>{humanize(car.priority)}</td><td>{humanize(car.status)}</td><td>{formatDate(issuedDate(car))}</td><td>{formatDate(agreedDue(car))}</td><td>{formatDate(closedDate(car))}</td><td><span className={`badge ${timeliness === "On time" ? "badge--success" : timeliness === "Late" || timeliness === "Overdue" ? "badge--danger" : "badge--neutral"}`}>{timeliness}</span></td><td><div>RCA: {humanize(car.root_cause_status)}</div><div>CAP: {humanize(car.capa_status)}</div></td><td><button className="btn btn--small" type="button" onClick={() => navigate(`/maintenance/${amoCode}/quality/cars?control=${encodeURIComponent(car.id)}`)}>Control</button></td></tr>;
          }) : <tr><td colSpan={10} className="muted">No CARs match the active filters.</td></tr>}</tbody></table></div>
        </section>
      </main>
    </DepartmentLayout>
  );
};

export default QmsCarPerformanceReportPage;
