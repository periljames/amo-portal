import React, { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
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
import { computeChi } from "./chi";
import { computeReadiness } from "./readiness";
import FindingDrawer from "./FindingDrawer";

type Props = {
  amoCode: string;
  department: string;
  scheduleId: string;
};

type Tab = "historical" | "checklists" | "documents";

type FindingRow = {
  finding: QMSFindingOut;
  audit: QMSAuditOut;
  linkedCar: CAROut | null;
};

const asStatus = (finding: QMSFindingOut): "Open" | "Closed" | "Overdue" => {
  if (finding.closed_at) return "Closed";
  if (finding.target_close_date && new Date(finding.target_close_date).getTime() < Date.now()) return "Overdue";
  return "Open";
};

const sparklinePath = (values: number[]): string => {
  if (values.length === 0) return "";
  const width = 180;
  const height = 48;
  const max = Math.max(...values, 100);
  const min = Math.min(...values, 0);
  const range = Math.max(max - min, 1);
  return values
    .map((value, idx) => {
      const x = (idx / Math.max(values.length - 1, 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${idx === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
};

const AuditDetailView: React.FC<Props> = ({ amoCode, department, scheduleId }) => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = (searchParams.get("tab") as Tab) || "historical";
  const severityFilter = searchParams.get("severity") || "ALL";
  const statusFilter = searchParams.get("status") || "ALL";
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
    return findingRows
      .filter((row) => severityFilter === "ALL" || row.finding.level === severityFilter)
      .filter((row) => statusFilter === "ALL" || asStatus(row.finding) === statusFilter)
      .sort((a, b) => b.finding.created_at.localeCompare(a.finding.created_at));
  }, [findingRows, severityFilter, statusFilter]);

  const selectedRow = useMemo(
    () => findingRows.find((row) => row.finding.id === selectedFindingId) ?? null,
    [findingRows, selectedFindingId]
  );

  const chi = useMemo(
    () =>
      computeChi(
        (findingsQueries.data ?? []).map((entry) => ({
          auditLabel: entry.audit.audit_ref,
          findings: entry.findings,
          createdAt: entry.audit.created_at,
        }))
      ),
    [findingsQueries.data]
  );

  const upcomingAudit = useMemo(() => {
    const planned = scheduleAudits
      .filter((audit) => audit.status !== "CLOSED")
      .sort((a, b) => (a.planned_start || "9999").localeCompare(b.planned_start || "9999"));
    return planned[0] ?? scheduleAudits[0] ?? null;
  }, [scheduleAudits]);

  const readiness = schedule ? computeReadiness(schedule, upcomingAudit) : null;
  const brand = getBrandContext();

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (!value || value === "ALL") next.delete(key);
    else next.set(key, value);
    setSearchParams(next);
  };

  const setTab = (tab: Tab) => {
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

  if (!schedule && !schedulesQuery.isLoading) {
    return (
      <div className="qms-card">
        <h3>Schedule not found</h3>
        <p>The schedule is missing, inactive, or outside your AMO scope.</p>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/list`)}>
          Back to list
        </button>
      </div>
    );
  }

  return (
    <div className="qms-audit-detail">
      <section className="qms-card">
        <div className="qms-audit-detail__breadcrumb">Audits &gt; {brand.name || amoCode} &gt; Schedule</div>
        <div className="qms-header__actions" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h2 className="qms-title" style={{ marginBottom: 0 }}>{schedule?.title || "Loading schedule..."}</h2>
            <p className="qms-subtitle">Audit War Room: readiness, findings, evidence and closure controls.</p>
          </div>
          <span className="qms-pill qms-pill--info">Audit Status: {upcomingAudit?.status || "PLANNED"}</span>
        </div>
      </section>

      <section className="qms-grid qms-audit-detail__intelligence">
        <article className="qms-card">
          <h4 style={{ marginTop: 0 }}>Compliance Health Index</h4>
          {findingsQueries.isLoading ? <div className="qms-skeleton-block" /> : (
            <>
              <div className="qms-audit-detail__score">{chi.score === null ? "—" : `${chi.score}%`}</div>
              <div className="qms-card__subtitle">Weighted score (Level 1: -5, Level 2: -2, Level 3: -0.5)</div>
              <svg viewBox="0 0 180 48" width="100%" height="48" aria-label="CHI trend">
                <path d={sparklinePath(chi.trend.map((point) => point.score ?? 100))} fill="none" stroke="#2563eb" strokeWidth="2" />
              </svg>
              <small>{chi.hasEnoughData ? chi.interpretation : "Insufficient historical audits for trend confidence."}</small>
            </>
          )}
        </article>

        <article className="qms-card">
          <h4 style={{ marginTop: 0 }}>AMO dossier</h4>
          {dashboardQuery.isLoading ? <div className="qms-skeleton-block" /> : (
            <div className="qms-grid" style={{ gap: 6 }}>
              <div><strong>Registered Name:</strong> {brand.name || amoCode}</div>
              <div><strong>Primary Quality Manager:</strong> {schedule?.lead_auditor_user_id || "Unassigned"}</div>
              <div>
                <strong>Risk Summary:</strong>{" "}
                {dashboardQuery.data?.findings_open_level_1
                  ? "High Risk: Technical Records"
                  : dashboardQuery.data?.findings_open_level_2
                  ? "Moderate Risk: Training"
                  : "Low Risk: Stores"}
              </div>
            </div>
          )}
        </article>

        <article className="qms-card">
          <h4 style={{ marginTop: 0 }}>Preparation Tracker</h4>
          {schedulesQuery.isLoading ? <div className="qms-skeleton-block" /> : (
            <>
              <div className="qms-meter__inner" style={{ width: "100%", height: 16, borderRadius: 999, background: "#e2e8f0" }}>
                <div style={{ width: `${readiness?.score ?? 0}%`, height: "100%", background: "#1d4ed8", borderRadius: 999 }} />
              </div>
              <div style={{ marginTop: 8, fontWeight: 700 }}>{readiness?.score ?? 0}% · {readiness?.label ?? "Loading"}</div>
              <small>Readiness combines checklist/report staging, scope quality and auditor assignment.</small>
            </>
          )}
        </article>
      </section>

      <section className="qms-card">
        <div className="qms-segmented" role="tablist" aria-label="Audit detail tabs" style={{ "--segment-count": 3, "--segment-active-index": activeTab === "historical" ? 0 : activeTab === "checklists" ? 1 : 2 } as React.CSSProperties}>
          <button type="button" className={activeTab === "historical" ? "is-active" : ""} onClick={() => setTab("historical")}>Historical Findings</button>
          <button type="button" className={activeTab === "checklists" ? "is-active" : ""} onClick={() => setTab("checklists")}>Live Checklists</button>
          <button type="button" className={activeTab === "documents" ? "is-active" : ""} onClick={() => setTab("documents")}>Document Library</button>
        </div>

        {activeTab === "historical" ? (
          <>
            <div className="qms-header__actions" style={{ marginTop: 12 }}>
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
            </div>

            {findingsQueries.isLoading ? <div className="qms-skeleton-row"><div /><div /><div /><div /></div> : null}
            {findingsQueries.isError ? <p className="text-danger">Failed to load historical findings.</p> : null}
            {!findingsQueries.isLoading && filteredRows.length === 0 ? <p>No findings match current filters.</p> : null}

            <table className="table" style={{ marginTop: 12 }}>
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
                  return (
                    <tr
                      key={row.finding.id}
                      className={active ? "qms-row--active" : ""}
                      onClick={() => openFinding(row.finding.id)}
                      style={{ cursor: "pointer" }}
                    >
                      <td>{row.finding.finding_ref ?? row.finding.id.slice(0, 8)}</td>
                      <td><code>{row.finding.requirement_ref ?? "N/A"}</code></td>
                      <td><span className="qms-pill">{row.finding.level}</span></td>
                      <td>{asStatus(row.finding)}</td>
                      <td>{row.finding.closed_at ? new Date(row.finding.closed_at).toLocaleDateString() : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        ) : activeTab === "checklists" ? (
          <div style={{ marginTop: 12 }}>
            <p>Checklist collaboration is linked from Audit Run Hub. Uploaded checklist status:</p>
            <p><strong>{upcomingAudit?.checklist_file_ref ? "Checklist attached" : "No checklist attached yet"}</strong></p>
            {upcomingAudit ? <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/${upcomingAudit.id}`)}>Open Run Hub</button> : null}
          </div>
        ) : (
          <div style={{ marginTop: 12 }}>
            <p>Review all reports/checklists and CAR attachments in the evidence library.</p>
            <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/evidence`)}>
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
