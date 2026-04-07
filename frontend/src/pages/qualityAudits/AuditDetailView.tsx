import React, { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Search, Info, ClipboardList } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getBrandContext } from "../../services/branding";
import {
  qmsGetDashboard,
  qmsListAudits,
  qmsListCars,
  qmsListFindings,
  qmsListAuditSchedules,
  type CAROut,
  type QMSAuditOut,
  type QMSFindingOut,
} from "../../services/qms";
import { computeReadiness } from "./readiness";
import { getDueMessage } from "./dueStatus";
import FindingDrawer from "./FindingDrawer";
import { selectRelevantDueAudit } from "../../utils/auditDate";

type Props = {
  amoCode: string;
  department: string;
  scheduleId: string;
};

type WorkspaceTab = "findings" | "checklists" | "documents";

type FindingRow = {
  finding: QMSFindingOut;
  audit: QMSAuditOut;
  linkedCar: CAROut | null;
};

type TrendDatum = {
  label: string;
  value: number;
};

const asStatus = (finding: QMSFindingOut): "Open" | "Closed" | "Overdue" => {
  if (finding.closed_at) return "Closed";
  if (finding.target_close_date && new Date(finding.target_close_date).getTime() < Date.now()) return "Overdue";
  return "Open";
};

const riskTone = (openLevel1: number, openLevel2: number) => {
  if (openLevel1 > 0) return { label: "High", className: "qms-pill qms-pill--danger" };
  if (openLevel2 > 0) return { label: "Moderate", className: "qms-pill qms-pill--warning" };
  return { label: "Low", className: "qms-pill qms-pill--success" };
};

const statusClassName = (status: "Open" | "Closed" | "Overdue") => {
  if (status === "Closed") return "qms-status-pill qms-status-pill--closed";
  if (status === "Overdue") return "qms-status-pill qms-status-pill--overdue";
  return "qms-status-pill qms-status-pill--open";
};

const TrendCard = React.memo(function TrendCard({ data, hasData }: { data: TrendDatum[]; hasData: boolean }) {
  return (
    <article className="qms-card qms-audit-detail__kpi-card">
      <div className="qms-audit-detail__kpi-title-row">
        <h4>Compliance Trend</h4>
        <span className="qms-audit-detail__tooltip" title="Trend Formula: monthly count of findings across this schedule.">
          <Info size={14} />
          Trend Formula Info
        </span>
      </div>
      <div className="qms-audit-detail__trend-wrap">
        <ResponsiveContainer width="100%" height={190}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" opacity={0.35} />
            <XAxis dataKey="label" tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
            <YAxis allowDecimals={false} tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
            <Tooltip />
            <Bar
              dataKey="value"
              fill={hasData ? "var(--accent-primary)" : "var(--text-muted)"}
              opacity={hasData ? 0.9 : 0.2}
              radius={[8, 8, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
        {!hasData ? (
          <div className="qms-audit-detail__trend-empty-copy">
            <strong>No trend data yet. Complete first audit to generate insights.</strong>
          </div>
        ) : null}
      </div>
    </article>
  );
});

const FindingsTable = React.memo(function FindingsTable({
  filteredRows,
  selectedFindingId,
  openFinding,
  onAddFirstFinding,
}: {
  filteredRows: FindingRow[];
  selectedFindingId: string | null;
  openFinding: (findingId: string) => void;
  onAddFirstFinding: () => void;
}) {
  if (filteredRows.length === 0) {
    return (
      <div className="qms-audit-detail__empty-findings">
        <ClipboardList size={30} />
        <h4>No findings recorded</h4>
        <p>No findings match your current schedule and filter criteria.</p>
        <button type="button" className="btn" onClick={onAddFirstFinding}>+ Add First Finding</button>
      </div>
    );
  }

  return (
    <div className="qms-audit-detail__table-wrap">
      <table className="table table--wrap">
        <thead>
          <tr>
            <th>ID</th>
            <th>Clause (KCAR / ISO)</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Closed Date</th>
          </tr>
        </thead>
        <tbody>
          {filteredRows.map((row) => {
            const active = selectedFindingId === row.finding.id;
            const status = asStatus(row.finding);
            return (
              <tr
                key={row.finding.id}
                className={active ? "qms-row--active qms-table__row" : "qms-table__row"}
                onClick={() => openFinding(row.finding.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openFinding(row.finding.id);
                  }
                }}
                tabIndex={0}
                role="button"
              >
                <td>{row.finding.finding_ref ?? row.finding.id.slice(0, 8)}</td>
                <td><code>{row.finding.requirement_ref ?? "N/A"}</code></td>
                <td><span className="qms-pill">{row.finding.level}</span></td>
                <td><span className={statusClassName(status)}>{status}</span></td>
                <td>{row.finding.closed_at ? new Date(row.finding.closed_at).toLocaleDateString() : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
});

const AuditDetailView: React.FC<Props> = ({ amoCode, department, scheduleId }) => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const rawWorkspaceTab = searchParams.get("tab");
  const activeTab: WorkspaceTab = rawWorkspaceTab === "checklists" || rawWorkspaceTab === "documents" ? rawWorkspaceTab : "findings";
  const severityFilter = searchParams.get("severity") || "ALL";
  const statusFilter = searchParams.get("status") || "ALL";
  const findingSearch = searchParams.get("q") || "";
  const selectedFindingId = searchParams.get("findingId");

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-schedules", amoCode],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }),
    staleTime: 60_000,
  });

  const auditsQuery = useQuery({
    queryKey: ["qms-audits", "schedule-detail", amoCode],
    queryFn: () => qmsListAudits({ domain: "AMO" }),
    staleTime: 60_000,
  });

  const carsQuery = useQuery({
    queryKey: ["qms-cars", "schedule-detail", amoCode],
    queryFn: () => qmsListCars({}),
    staleTime: 60_000,
  });

  const dashboardQuery = useQuery({
    queryKey: ["qms-dashboard", "schedule-detail", amoCode],
    queryFn: () => qmsGetDashboard({ domain: "AMO" }),
    staleTime: 60_000,
  });

  const schedule = useMemo(
    () => (schedulesQuery.data ?? []).find((row) => row.id === scheduleId) ?? null,
    [scheduleId, schedulesQuery.data]
  );

  const scheduleAudits = useMemo(() => {
    const all = auditsQuery.data ?? [];
    if (!schedule) return [];
    const byTitle = all.filter((audit) => audit.title.trim().toLowerCase() === schedule.title.trim().toLowerCase());
    if (byTitle.length > 0) return byTitle;
    return all.filter((audit) => audit.kind === schedule.kind);
  }, [auditsQuery.data, schedule]);

  const findingsQueries = useQuery({
    queryKey: ["qms-findings", "schedule-detail", amoCode, scheduleId, scheduleAudits.map((item) => item.id).join(",")],
    queryFn: async () => {
      const rows = await Promise.all(
        scheduleAudits.map(async (audit) => ({
          audit,
          findings: await qmsListFindings(audit.id),
        }))
      );
      return rows;
    },
    enabled: scheduleAudits.length > 0,
    staleTime: 60_000,
  });

  const findingRows = useMemo<FindingRow[]>(() => {
    const carsByFinding = new Map<string, CAROut>();
    (carsQuery.data ?? []).forEach((car) => {
      if (car.finding_id && !carsByFinding.has(car.finding_id)) {
        carsByFinding.set(car.finding_id, car);
      }
    });

    return (findingsQueries.data ?? []).flatMap(({ audit, findings }) =>
      findings.map((finding) => ({
        finding,
        audit,
        linkedCar: carsByFinding.get(finding.id) ?? null,
      }))
    );
  }, [carsQuery.data, findingsQueries.data]);

  const filteredRows = useMemo(() => {
    const q = findingSearch.trim().toLowerCase();
    return findingRows
      .filter((row) => severityFilter === "ALL" || row.finding.level === severityFilter)
      .filter((row) => statusFilter === "ALL" || asStatus(row.finding) === statusFilter)
      .filter((row) => {
        if (!q) return true;
        return [row.finding.finding_ref, row.finding.requirement_ref, row.finding.description]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(q);
      })
      .sort((a, b) => b.finding.created_at.localeCompare(a.finding.created_at));
  }, [findingRows, severityFilter, statusFilter, findingSearch]);

  const selectedRow = useMemo(
    () => findingRows.find((row) => row.finding.id === selectedFindingId) ?? null,
    [findingRows, selectedFindingId]
  );

  const [tick, setTick] = useState(Date.now());
  useEffect(() => { const id = window.setInterval(() => setTick(Date.now()), 60_000); return () => window.clearInterval(id); }, []);

  const upcomingAudit = useMemo(
    () => selectRelevantDueAudit(scheduleAudits, new Date(tick)) ?? scheduleAudits[0] ?? null,
    [scheduleAudits, tick],
  );

  const trendData = useMemo<TrendDatum[]>(() => {
    const grouped = new Map<string, number>();
    findingRows.forEach((row) => {
      const key = row.finding.created_at.slice(0, 7);
      grouped.set(key, (grouped.get(key) ?? 0) + 1);
    });
    if (grouped.size === 0) {
      return [];
    }
    return Array.from(grouped.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-6)
      .map(([label, value]) => ({ label: label.slice(5), value }));
  }, [findingRows]);

  const [clockMs, setClockMs] = useState(Date.now());
  useEffect(() => { const id = window.setInterval(() => setClockMs(Date.now()), 60_000); return () => window.clearInterval(id); }, []);
  const readiness = schedule ? computeReadiness(schedule, upcomingAudit) : null;
  const dueBanner = getDueMessage(new Date(clockMs), schedule?.next_due_date, upcomingAudit?.planned_start, upcomingAudit?.planned_end);
  const brand = getBrandContext();
  const dashboard = dashboardQuery.data;
  const risk = riskTone(dashboard?.findings_open_level_1 ?? 0, dashboard?.findings_open_level_2 ?? 0);

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (!value || value === "ALL") next.delete(key);
    else next.set(key, value);
    setSearchParams(next);
  };

  const setTab = (tab: WorkspaceTab) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    setSearchParams(next);
  };

  const openFinding = (findingId: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("findingId", findingId);
    setSearchParams(next);
  };

  const closeFinding = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("findingId");
    setSearchParams(next);
  };

  const clearFilters = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("severity");
    next.delete("status");
    next.delete("q");
    setSearchParams(next);
  };

  const baseQmsPath = `/maintenance/${amoCode}/${department}/qms`;
  const goToRegister = () => navigate(`${baseQmsPath}/audits/register`);
  const goToEvidence = () => navigate(`${baseQmsPath}/evidence`);

  if (!schedule && !schedulesQuery.isLoading) {
    return (
      <div className="qms-card">
        <h3>Schedule not found</h3>
        <p>The schedule is missing, inactive, or outside your AMO scope.</p>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/plan?view=list`)}>
          Back to list
        </button>
      </div>
    );
  }

  return (
    <div className="qms-audit-detail">
      {dueBanner ? (
        <section className="qms-card" style={{ marginBottom: 12 }}>
          <strong>{dueBanner.label}</strong>
          <div className="text-muted">
            Next due: {schedule?.next_due_date || "—"} · Upcoming notice: {upcomingAudit?.upcoming_notice_sent_at || "—"} · Day-of notice: {upcomingAudit?.day_of_notice_sent_at || "—"}
          </div>
        </section>
      ) : null}

      <section className="qms-card qms-audit-detail__hero">
        <div className="qms-audit-detail__breadcrumb">Audits &gt; {brand.name || amoCode} &gt; {schedule?.title || "Schedule"}</div>
        <div className="qms-audit-detail__hero-grid">
          <div>
            <h1 className="qms-audit-detail__title">Schedule Detail</h1>
            <h2 className="qms-audit-detail__audit-name">{schedule?.title || "Loading audit..."}</h2>
          </div>
          <div className="qms-audit-detail__hero-actions">
            <span className="qms-pill qms-pill--info">{upcomingAudit?.status || "PLANNED"}</span>
            <div
              className="qms-segmented"
              role="tablist"
              aria-label="Audit route tabs"
              style={{ "--segment-count": 3, "--segment-active-index": 0 } as React.CSSProperties}
            >
              <button type="button" className="is-active" onClick={() => navigate(`${baseQmsPath}/audits/plan?view=calendar`)}>Plan</button>
              <button type="button" onClick={goToRegister}>Register</button>
              <button type="button" onClick={goToEvidence}>Evidence</button>
            </div>
          </div>
        </div>

        <div className="qms-audit-detail__kpi-grid">
          <article className="qms-card qms-audit-detail__kpi-card">
            <h4>Preparation Status</h4>
            <div className="qms-audit-detail__prep-bar">
              <span style={{ width: `${readiness?.score ?? 0}%` }} />
            </div>
            <div className="qms-audit-detail__prep-meta">Steps Complete: {Math.round(((readiness?.score ?? 0) / 100) * 5)} of 5</div>
            <small>{readiness?.label ?? "Loading"}</small>
            <button type="button" className="btn qms-audit-detail__prep-cta">Start Preparation Steps</button>
          </article>

          <article className="qms-card qms-audit-detail__kpi-card">
            <h4>AMO Dossier</h4>
            <div className="qms-audit-detail__dossier-list">
              <div><strong>Registered Name:</strong> {brand.name || amoCode}</div>
              <div>
                <strong>Lead auditor:</strong>{" "}
                {schedule?.lead_auditor_user_id || "Unassigned"}
              </div>
              <div><strong>Auditee:</strong> {schedule?.auditee || "Unassigned"}</div>
              <div><strong>Observer auditor:</strong> {schedule?.observer_auditor_user_id || "Unassigned"}</div>
              <div><strong>Assistant auditor:</strong> {schedule?.assistant_auditor_user_id || "Unassigned"}</div>
              <div>
                <strong>Risk Summary:</strong> <span className={risk.className}>{risk.label}</span>
              </div>
              <div><strong>Schedule Frequency:</strong> {schedule?.frequency?.replaceAll("_", " ") || "—"}</div>
            </div>
          </article>

          <TrendCard data={trendData} hasData={findingRows.length > 0} />
        </div>
      </section>

      <section className="qms-card">
        <div className="qms-audit-detail__workspace-tabs" role="tablist" aria-label="Audit detail workspace tabs">
          <button type="button" className={activeTab === "findings" ? "is-active" : ""} onClick={() => setTab("findings")}>Findings</button>
          <button type="button" className={activeTab === "checklists" ? "is-active" : ""} onClick={() => setTab("checklists")}>Checklists</button>
          <button type="button" className={activeTab === "documents" ? "is-active" : ""} onClick={() => setTab("documents")}>Document Library</button>
        </div>

        {activeTab === "findings" ? (
          <>
            <div className="qms-audit-detail__control-bar" style={{ marginTop: 12 }}>
              <label className="qms-audit-detail__search">
                <Search size={14} />
                <input
                  value={findingSearch}
                  onChange={(e) => setFilter("q", e.target.value)}
                  placeholder="Search findings, clause or description"
                />
              </label>
              <label className="qms-pill">Severity
                <select value={severityFilter} onChange={(e) => setFilter("severity", e.target.value)}>
                  <option value="ALL">All</option>
                  <option value="LEVEL_1">Level 1</option>
                  <option value="LEVEL_2">Level 2</option>
                  <option value="LEVEL_3">Level 3</option>
                </select>
              </label>
              <label className="qms-pill">Status
                <select value={statusFilter} onChange={(e) => setFilter("status", e.target.value)}>
                  <option value="ALL">All</option>
                  <option value="Open">Open</option>
                  <option value="Closed">Closed</option>
                  <option value="Overdue">Overdue</option>
                </select>
              </label>
              <button type="button" className="secondary-chip-btn" onClick={clearFilters}>Clear filters</button>
            </div>
            <p className="qms-audit-detail__results-meta">{filteredRows.length} finding(s) shown</p>

            {findingsQueries.isLoading ? <div className="qms-skeleton-row"><div /><div /><div /><div /></div> : null}
            {findingsQueries.isError ? <p className="text-danger">Failed to load findings.</p> : null}
            {!findingsQueries.isLoading ? (
              <FindingsTable
                filteredRows={filteredRows}
                selectedFindingId={selectedFindingId}
                openFinding={openFinding}
                onAddFirstFinding={() => navigate(`${baseQmsPath}/audits/register?tab=findings`)}
              />
            ) : null}
          </>
        ) : activeTab === "checklists" ? (
          <div style={{ marginTop: 12 }}>
            <p><strong>{upcomingAudit?.checklist_file_ref ? "Checklist attached" : "No checklist attached yet"}</strong></p>
            {upcomingAudit ? <button type="button" className="secondary-chip-btn" onClick={() => navigate(`${baseQmsPath}/audits/${upcomingAudit.id}`)}>Open Run Hub</button> : null}
          </div>
        ) : (
          <div style={{ marginTop: 12 }}>
            <p>Review all reports/checklists and CAR attachments in the evidence library.</p>
            <button type="button" className="secondary-chip-btn" onClick={() => navigate(`${baseQmsPath}/evidence`)}>
              Open Document Library
            </button>
          </div>
        )}
      </section>

      <FindingDrawer
        isOpen={!!selectedFindingId}
        amoCode={amoCode}
        department={department}
        finding={selectedRow?.finding ?? null}
        linkedCar={selectedRow?.linkedCar ?? null}
        onClose={closeFinding}
      />
    </div>
  );
};

export default AuditDetailView;
