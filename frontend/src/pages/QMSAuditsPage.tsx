import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import DataTableShell from "../components/shared/DataTableShell";
import SpreadsheetToolbar from "../components/shared/SpreadsheetToolbar";
import EmptyState from "../components/shared/EmptyState";
import InlineError from "../components/shared/InlineError";
import { getContext } from "../services/auth";
import { qmsListAudits, type QMSAuditOut } from "../services/qms";

type LoadState = "idle" | "loading" | "ready" | "error";
type UiStatus = "open" | "pending" | "closed" | "overdue" | "escalated";
type TimeWindow = "week" | "month" | "custom";

const SUPPORTED_STATUS = ["open", "planned", "in_progress", "cap_open", "closed"] as const;

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
      const data = await qmsListAudits({ domain: "AMO" });
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
    if (statusValues.length) {
      next.set("status", statusValues.join(","));
    } else {
      next.delete("status");
    }

    if (selectedUiStatus.length) next.set("uiStatus", selectedUiStatus.join(","));
    else next.delete("uiStatus");

    setSearchParams(next, { replace: true });
  }, [searchParams, selectedUiStatus, setSearchParams]);

  const { startDate, endDate } = useMemo(() => {
    const now = new Date();
    if (timeWindow === "week") {
      const start = new Date(now);
      start.setDate(now.getDate() - now.getDay());
      const end = new Date(start);
      end.setDate(start.getDate() + 6);
      return { startDate: start, endDate: end };
    }
    if (timeWindow === "custom") {
      return {
        startDate: asDate(customStart) ?? new Date("2000-01-01"),
        endDate: asDate(customEnd) ?? new Date("2100-01-01"),
      };
    }
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    return { startDate: start, endDate: end };
  }, [timeWindow, customEnd, customStart]);

  const recentFiltered = useMemo(() => {
    const now = new Date();
    const rows = [...audits]
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
      .sort((a, b) => (asDate(b.planned_start)?.getTime() ?? 0) - (asDate(a.planned_start)?.getTime() ?? 0));
    return rows.slice(0, 10);
  }, [audits, endDate, selectedUiStatus, startDate, tableFilter.kind, tableFilter.owner, tableFilter.title]);

  const toggleUiStatus = (value: UiStatus) => {
    setSelectedUiStatus((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]
    );
  };

  return (
    <QMSLayout
      amoCode={amoCode}
      department={department}
      title="Audits & Inspections"
      subtitle="Recent audits with operational filters and direct drilldown to run hubs."
      actions={
        <div className="qms-header__actions">
          <button type="button" className="btn btn-primary" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/calendar`)}>
            Plan / Schedule audits
          </button>
          <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/events?entity=qms.audit`)}>
            View activity history
          </button>
        </div>
      }
    >
      <DataTableShell
        title="Recent audits (last 10)"
        actions={
          <div className="qms-header__actions" style={{ flexDirection: "column", alignItems: "stretch" }}>
            <div className="qms-header__actions">
              <label className="qms-pill">Window
                <select value={timeWindow} onChange={(e) => setTimeWindow(e.target.value as TimeWindow)}>
                  <option value="week">This week</option>
                  <option value="month">This month</option>
                  <option value="custom">Custom range</option>
                </select>
              </label>
              {timeWindow === "custom" ? (
                <>
                  <input type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)} />
                  <input type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} />
                </>
              ) : null}
              {(["open", "pending", "closed", "overdue", "escalated"] as UiStatus[]).map((status) => (
                <button key={status} type="button" className={`secondary-chip-btn${selectedUiStatus.includes(status) ? " is-active" : ""}`} onClick={() => toggleUiStatus(status)}>
                  {status}
                </button>
              ))}
            </div>
            <SpreadsheetToolbar
              density={density}
              onDensityChange={setDensity}
              wrapText={wrapText}
              onWrapTextChange={setWrapText}
              showFilters={showFilters}
              onShowFiltersChange={setShowFilters}
              columnToggles={[
                { id: "owner", label: "Lead auditor", checked: showOwnerColumn, onToggle: () => setShowOwnerColumn((v) => !v) },
              ]}
            />
          </div>
        }
      >
        {state === "loading" && <p>Loading audits…</p>}
        {state === "error" && <InlineError message={error || "Unable to load audits."} onAction={() => void load()} />}
        {state === "ready" && (
          <table className={`table ${density === "compact" ? "table-row--compact" : "table-row--comfortable"} ${wrapText ? "table--wrap" : ""}`}>
            <thead>
              <tr>
                <th>Audit</th>
                <th>Kind</th>
                <th>Status</th>
                <th>Start</th>
                <th>End</th>
                {showOwnerColumn ? <th>Lead auditor</th> : null}
              </tr>
              {showFilters ? <tr>
                <th><input className="input" style={{ height: 30 }} placeholder="Filter title" value={tableFilter.title} onChange={(e) => setTableFilter((p) => ({ ...p, title: e.target.value }))} /></th>
                <th><input className="input" style={{ height: 30 }} placeholder="Filter kind" value={tableFilter.kind} onChange={(e) => setTableFilter((p) => ({ ...p, kind: e.target.value }))} /></th>
                <th></th>
                <th></th>
                <th></th>
                {showOwnerColumn ? <th><input className="input" style={{ height: 30 }} placeholder="Filter owner" value={tableFilter.owner} onChange={(e) => setTableFilter((p) => ({ ...p, owner: e.target.value }))} /></th> : null}
              </tr> : null}
            </thead>
            <tbody>
              {recentFiltered.map((audit) => (
                <tr key={audit.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/${audit.id}`)}>
                  <td>
                    <strong>{audit.title}</strong>
                    <div className="text-muted">{audit.audit_ref}</div>
                  </td>
                  <td>{audit.kind}</td>
                  <td><span className="qms-pill">{audit.status}</span></td>
                  <td>{fmt(audit.planned_start)}</td>
                  <td>{fmt(audit.planned_end)}</td>
                  {showOwnerColumn ? <td>{audit.lead_auditor_user_id ?? "Unassigned"}</td> : null}
                </tr>
              ))}
              {recentFiltered.length === 0 && (
                <tr>
                  <td colSpan={showOwnerColumn ? 6 : 5}>
                    <EmptyState
                      title="No recent audits in this filter"
                      description="Change time window or status filters to broaden results."
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </DataTableShell>
    </QMSLayout>
  );
};

export default QMSAuditsPage;
