import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import QMSLayout from "../components/QMS/QMSLayout";
import DataTableShell from "../components/shared/DataTableShell";
import SpreadsheetToolbar from "../components/shared/SpreadsheetToolbar";
import EmptyState from "../components/shared/EmptyState";
import InlineError from "../components/shared/InlineError";
import SectionCard from "../components/shared/SectionCard";
import Button from "../components/UI/Button";
import { getContext } from "../services/auth";
import { qmsListAudits, type QMSAuditOut } from "../services/qms";
import { buildAuditWorkspacePath } from "../utils/auditSlug";

type LoadState = "idle" | "loading" | "ready" | "error";
type UiStatus = "open" | "pending" | "closed" | "overdue" | "escalated";
type TimeWindow = "week" | "month" | "quarter" | "year" | "custom";

const SUPPORTED_STATUS = ["open", "planned", "in_progress", "cap_open", "closed"] as const;
const QUARTERS = [
  { value: 1, label: "Q1 · Jan–Mar" },
  { value: 2, label: "Q2 · Apr–Jun" },
  { value: 3, label: "Q3 · Jul–Sep" },
  { value: 4, label: "Q4 · Oct–Dec" },
] as const;

function asDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

function fmt(value: string | null | undefined): string {
  const d = asDate(value);
  return d ? d.toLocaleDateString() : "—";
}

function inWindow(row: QMSAuditOut, start: Date, end: Date): boolean {
  const s = asDate(row.planned_start);
  const e = asDate(row.planned_end) ?? s;
  if (!s && !e) return false;
  const low = s ?? e!;
  const high = e ?? s!;
  return high >= start && low <= end;
}

function auditStatusClass(value: string): string {
  const normalized = value.toUpperCase();
  if (normalized === "CLOSED") return "qms-pill qms-pill--success";
  if (normalized === "CAP_OPEN" || normalized === "IN_PROGRESS") return "qms-pill qms-pill--warning";
  if (normalized === "PLANNED") return "qms-pill qms-pill--info";
  return "qms-pill";
}

function yearOptions(audits: QMSAuditOut[]): number[] {
  const set = new Set<number>();
  audits.forEach((audit) => {
    const d = asDate(audit.planned_start) ?? asDate(audit.planned_end);
    if (d) set.add(d.getFullYear());
  });
  const currentYear = new Date().getFullYear();
  set.add(currentYear - 1);
  set.add(currentYear);
  set.add(currentYear + 1);
  return Array.from(set).sort((a, b) => a - b);
}

function countdownLabel(audit: QMSAuditOut): { text: string; className: string } {
  const target = asDate(audit.planned_start) ?? asDate(audit.planned_end);
  if (!target) return { text: "Date pending", className: "audit-countdown-chip" };
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  target.setHours(0, 0, 0, 0);
  const diffDays = Math.round((target.getTime() - today.getTime()) / 86_400_000);
  if (diffDays < 0) return { text: `${Math.abs(diffDays)} day(s) overdue`, className: "audit-countdown-chip is-overdue" };
  if (diffDays === 0) return { text: "Due today", className: "audit-countdown-chip is-due-soon" };
  if (diffDays <= 14) return { text: `Starts in ${diffDays} day(s)`, className: "audit-countdown-chip is-due-soon" };
  return { text: `Starts in ${diffDays} day(s)`, className: "audit-countdown-chip" };
}

const QMSAuditsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const [searchParams, setSearchParams] = useSearchParams();

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [audits, setAudits] = useState<QMSAuditOut[]>([]);
  const [timeWindow, setTimeWindow] = useState<TimeWindow>("month");
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [selectedQuarter, setSelectedQuarter] = useState<1 | 2 | 3 | 4>(Math.floor(new Date().getMonth() / 3 + 1) as 1 | 2 | 3 | 4);
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [selectedUiStatus, setSelectedUiStatus] = useState<UiStatus[]>(() => {
    const raw = searchParams.get("uiStatus");
    if (!raw) return [];
    return raw.split(",").filter(Boolean) as UiStatus[];
  });
  const [tableFilter, setTableFilter] = useState({ title: "", kind: "", owner: "" });
  const [density, setDensity] = useState<"compact" | "comfortable">("compact");
  const [wrapText, setWrapText] = useState(false);
  const [showFilters, setShowFilters] = useState(true);
  const [showOwnerColumn, setShowOwnerColumn] = useState(true);

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const data = await qmsListAudits({ domain: "AMO", limit: 400 }, { silent: true });
      setAudits(data);
      setState("ready");
    } catch (e: any) {
      setError(e?.message || "Failed to load audits.");
      setState("error");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    const mapped = new Set<string>();
    if (selectedUiStatus.includes("open")) {
      mapped.add("open");
      mapped.add("in_progress");
      mapped.add("cap_open");
    }
    if (selectedUiStatus.includes("pending")) mapped.add("planned");
    if (selectedUiStatus.includes("closed")) mapped.add("closed");

    const statusValues = Array.from(mapped).filter((v) => SUPPORTED_STATUS.includes(v as any));
    if (statusValues.length) next.set("status", statusValues.join(","));
    else next.delete("status");

    if (selectedUiStatus.length) next.set("uiStatus", selectedUiStatus.join(","));
    else next.delete("uiStatus");

    setSearchParams(next, { replace: true });
  }, [searchParams, selectedUiStatus, setSearchParams]);

  const availableYears = useMemo(() => yearOptions(audits), [audits]);

  const { startDate, endDate, windowLabel } = useMemo(() => {
    const now = new Date();
    if (timeWindow === "week") {
      const start = new Date(now);
      start.setDate(now.getDate() - now.getDay());
      const end = new Date(start);
      end.setDate(start.getDate() + 6);
      return { startDate: start, endDate: end, windowLabel: "This week" };
    }
    if (timeWindow === "year") {
      return {
        startDate: new Date(selectedYear, 0, 1),
        endDate: new Date(selectedYear, 11, 31),
        windowLabel: `${selectedYear}`,
      };
    }
    if (timeWindow === "quarter") {
      const quarterStartMonth = (selectedQuarter - 1) * 3;
      return {
        startDate: new Date(selectedYear, quarterStartMonth, 1),
        endDate: new Date(selectedYear, quarterStartMonth + 3, 0),
        windowLabel: `Q${selectedQuarter} ${selectedYear}`,
      };
    }
    if (timeWindow === "custom") {
      return {
        startDate: asDate(customStart) ?? new Date("2000-01-01"),
        endDate: asDate(customEnd) ?? new Date("2100-01-01"),
        windowLabel: "Custom range",
      };
    }
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    return { startDate: start, endDate: end, windowLabel: "This month" };
  }, [customEnd, customStart, selectedQuarter, selectedYear, timeWindow]);

  const recentFiltered = useMemo(() => {
    const now = new Date();
    return [...audits]
      .filter((row) => inWindow(row, startDate, endDate))
      .filter((row) => {
        if (!selectedUiStatus.length) return true;
        return selectedUiStatus.every((status) => {
          if (status === "pending") return row.status === "PLANNED";
          if (status === "open") return ["IN_PROGRESS", "CAP_OPEN", "PLANNED"].includes(row.status);
          if (status === "closed") return row.status === "CLOSED";
          if (status === "overdue") {
            const cutoff = asDate(row.planned_end) ?? asDate(row.planned_start);
            return !!cutoff && cutoff < now && row.status !== "CLOSED";
          }
          if (status === "escalated") {
            const anyRow = row as unknown as Record<string, unknown>;
            return Boolean(anyRow.escalation_level || anyRow.escalated || anyRow.is_escalated);
          }
          return true;
        });
      })
      .filter((row) => row.title.toLowerCase().includes(tableFilter.title.toLowerCase()))
      .filter((row) => row.kind.toLowerCase().includes(tableFilter.kind.toLowerCase()))
      .filter((row) => (row.lead_auditor_user_id ?? "").toLowerCase().includes(tableFilter.owner.toLowerCase()))
      .sort((a, b) => (asDate(a.planned_start)?.getTime() ?? 0) - (asDate(b.planned_start)?.getTime() ?? 0));
  }, [audits, endDate, selectedUiStatus, startDate, tableFilter.kind, tableFilter.owner, tableFilter.title]);

  const topRows = recentFiltered.slice(0, 10);

  const toggleUiStatus = (value: UiStatus) => {
    setSelectedUiStatus((prev) => (prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]));
  };

  const summaryItems = useMemo(() => {
    const overdue = audits.filter((row) => {
      const cutoff = asDate(row.planned_end) ?? asDate(row.planned_start);
      return cutoff && cutoff < new Date() && row.status !== "CLOSED";
    }).length;
    return [
      { label: "Visible audits", value: String(recentFiltered.length) },
      { label: "Window", value: windowLabel },
      { label: "Status", value: selectedUiStatus.length ? selectedUiStatus.join(", ") : "All" },
      { label: "Overdue overall", value: String(overdue) },
    ];
  }, [audits, recentFiltered.length, selectedUiStatus, windowLabel]);

  return (
    <QMSLayout
      amoCode={amoCode}
      department={department}
      title="Audits & Inspections"
      subtitle="Direct access to the register, planning, and current audit workspace."
      actions={
        <>
          <Button onClick={() => navigate(`/maintenance/${amoCode}/qms/audits/plan`)}>Plan audit</Button>
          <Button variant="secondary" onClick={() => navigate(`/maintenance/${amoCode}/qms/audits/register?tab=findings`)}>
            Register & closeout
          </Button>
          <Button variant="secondary" onClick={() => navigate(`/maintenance/${amoCode}/qms/audits/register`)}>
            Register
          </Button>
        </>
      }
    >
      <div className="qms-page-grid">
        <SectionCard variant="subtle" className="qms-compact-toolbar-card">
          <div className="qms-toolbar-stack">
            <div className="qms-toolbar qms-toolbar--portal qms-toolbar--with-pills">
              <label className="qms-field qms-field--compact">
                <span>Window range</span>
                <select value={timeWindow} onChange={(e) => setTimeWindow(e.target.value as TimeWindow)}>
                  <option value="week">This week</option>
                  <option value="month">This month</option>
                  <option value="quarter">Quarter</option>
                  <option value="year">Year</option>
                  <option value="custom">Custom range</option>
                </select>
              </label>
              {timeWindow === "year" || timeWindow === "quarter" ? (
                <label className="qms-field qms-field--compact">
                  <span>Year</span>
                  <select value={selectedYear} onChange={(e) => setSelectedYear(Number(e.target.value))}>
                    {availableYears.map((year) => (
                      <option key={year} value={year}>{year}</option>
                    ))}
                  </select>
                </label>
              ) : null}
              {timeWindow === "quarter" ? (
                <label className="qms-field qms-field--compact">
                  <span>Quarter</span>
                  <select value={selectedQuarter} onChange={(e) => setSelectedQuarter(Number(e.target.value) as 1 | 2 | 3 | 4)}>
                    {QUARTERS.map((quarter) => (
                      <option key={quarter.value} value={quarter.value}>{quarter.label}</option>
                    ))}
                  </select>
                </label>
              ) : null}
              {timeWindow === "custom" ? (
                <>
                  <label className="qms-field qms-field--compact">
                    <span>Start</span>
                    <input type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)} />
                  </label>
                  <label className="qms-field qms-field--compact">
                    <span>End</span>
                    <input type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} />
                  </label>
                </>
              ) : null}
              <div className="portal-pill-group">
                {(["open", "pending", "closed", "overdue", "escalated"] as UiStatus[]).map((status) => (
                  <button
                    key={status}
                    type="button"
                    className={`portal-pill-toggle${selectedUiStatus.includes(status) ? " is-active" : ""}`}
                    onClick={() => toggleUiStatus(status)}
                  >
                    {status}
                  </button>
                ))}
              </div>
              <Button variant="secondary" size="sm" onClick={() => void load()}>
                <RefreshCw size={15} />
                Refresh
              </Button>
            </div>
            <SpreadsheetToolbar
              density={density}
              onDensityChange={setDensity}
              wrapText={wrapText}
              onWrapTextChange={setWrapText}
              showFilters={showFilters}
              onShowFiltersChange={setShowFilters}
              columnToggles={[
                {
                  id: "owner",
                  label: "Lead auditor",
                  checked: showOwnerColumn,
                  onToggle: () => setShowOwnerColumn((v) => !v),
                },
              ]}
            />
          </div>
        </SectionCard>

        <SectionCard variant="subtle">
          <div className="portal-summary-strip">
            {summaryItems.map((item) => (
              <div key={item.label} className="portal-summary-chip">
                <span className="portal-summary-chip__label">{item.label}</span>
                <strong className="portal-summary-chip__value">{item.value}</strong>
              </div>
            ))}
          </div>
        </SectionCard>

        <DataTableShell title="Recent audits" actions={<span className="qms-table-meta">Click a row to open the workspace</span>}>
          {state === "loading" ? <p className="qms-loading-copy">Loading audits…</p> : null}
          {state === "error" ? <InlineError message={error || "Unable to load audits."} onAction={() => void load()} /> : null}
          {state === "ready" ? (
            topRows.length ? (
              <div className="table-responsive">
                <table className={`table table--portal ${density === "compact" ? "table-row--compact" : "table-row--comfortable"} ${wrapText ? "table--wrap" : ""}`}>
                  <thead>
                    <tr>
                      <th>Audit</th>
                      <th>Kind</th>
                      <th>Status</th>
                      <th>Window</th>
                      <th>Schedule</th>
                      {showOwnerColumn ? <th>Lead auditor</th> : null}
                    </tr>
                    {showFilters ? (
                      <tr>
                        <th>
                          <input className="input qms-input--filter" placeholder="Filter title" value={tableFilter.title} onChange={(e) => setTableFilter((p) => ({ ...p, title: e.target.value }))} />
                        </th>
                        <th>
                          <input className="input qms-input--filter" placeholder="Filter kind" value={tableFilter.kind} onChange={(e) => setTableFilter((p) => ({ ...p, kind: e.target.value }))} />
                        </th>
                        <th />
                        <th />
                        <th />
                        {showOwnerColumn ? (
                          <th>
                            <input className="input qms-input--filter" placeholder="Filter owner" value={tableFilter.owner} onChange={(e) => setTableFilter((p) => ({ ...p, owner: e.target.value }))} />
                          </th>
                        ) : null}
                      </tr>
                    ) : null}
                  </thead>
                  <tbody>
                    {topRows.map((audit) => {
                      const countdown = countdownLabel(audit);
                      return (
                        <tr key={audit.id} className="table-row--interactive" onClick={() => navigate(buildAuditWorkspacePath({ amoCode, department, auditRef: audit.audit_ref }))}>
                          <td>
                            <div className="table-primary-cell">
                              <strong>{audit.title}</strong>
                              <span>{audit.audit_ref}</span>
                            </div>
                          </td>
                          <td>{audit.kind}</td>
                          <td><span className={auditStatusClass(audit.status)}>{audit.status.replaceAll("_", " ")}</span></td>
                          <td>{fmt(audit.planned_start)} — {fmt(audit.planned_end)}</td>
                          <td><span className={countdown.className}>{countdown.text}</span></td>
                          {showOwnerColumn ? <td>{audit.lead_auditor_user_id ?? "Unassigned"}</td> : null}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="No audits in this range" description="Change the window range or status filters to broaden the result set." />
            )
          ) : null}
        </DataTableShell>
      </div>
    </QMSLayout>
  );
};

export default QMSAuditsPage;
