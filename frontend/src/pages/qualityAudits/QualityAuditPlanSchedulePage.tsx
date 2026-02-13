import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import EmptyState from "../../components/shared/EmptyState";
import DataTableShell from "../../components/shared/DataTableShell";
import SpreadsheetToolbar from "../../components/shared/SpreadsheetToolbar";
import { getContext } from "../../services/auth";
import { qmsListAudits, qmsListAuditSchedules, type QMSAuditScheduleOut } from "../../services/qms";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";

type PlannerView = "calendar" | "list" | "content";

type Props = {
  defaultView: PlannerView;
};

const QualityAuditPlanSchedulePage: React.FC<Props> = ({ defaultView }) => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const navigate = useNavigate();
  const [view, setView] = useState<PlannerView>(defaultView);
  const [density, setDensity] = useState<"compact" | "comfortable">("compact");
  const [wrapText, setWrapText] = useState(false);
  const [showFilters, setShowFilters] = useState(true);
  const [showOwnerColumn, setShowOwnerColumn] = useState(true);
  const [listFilter, setListFilter] = useState({ title: "", frequency: "", owner: "" });
  const [contentFilter, setContentFilter] = useState("");

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-schedules", amoCode],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }),
    staleTime: 60_000,
  });

  const auditsQuery = useQuery({
    queryKey: ["qms-audits", "planner", amoCode],
    queryFn: () => qmsListAudits({ domain: "AMO" }),
    staleTime: 60_000,
  });

  const groupedCalendar = useMemo(() => {
    const map = new Map<string, QMSAuditScheduleOut[]>();
    (schedulesQuery.data ?? []).forEach((schedule) => {
      const bucket = map.get(schedule.next_due_date) ?? [];
      bucket.push(schedule);
      map.set(schedule.next_due_date, bucket);
    });
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [schedulesQuery.data]);

  const contentRows = useMemo(
    () =>
      (schedulesQuery.data ?? []).map((schedule) => ({
        kind: "schedule" as const,
        id: schedule.id,
        title: schedule.title,
        date: schedule.next_due_date,
        status: schedule.is_active ? "ACTIVE" : "INACTIVE",
        owner: schedule.lead_auditor_user_id ?? "Unassigned",
      })),
    [schedulesQuery.data]
  );

  const filteredSchedules = useMemo(() => {
    return (schedulesQuery.data ?? [])
      .filter((row) => row.title.toLowerCase().includes(listFilter.title.toLowerCase()))
      .filter((row) => row.frequency.toLowerCase().includes(listFilter.frequency.toLowerCase()))
      .filter((row) => (row.lead_auditor_user_id ?? "").toLowerCase().includes(listFilter.owner.toLowerCase()));
  }, [listFilter.frequency, listFilter.owner, listFilter.title, schedulesQuery.data]);

  const filteredContentRows = useMemo(() => {
    const q = contentFilter.trim().toLowerCase();
    if (!q) return contentRows;
    return contentRows.filter((row) => `${row.title} ${row.status} ${row.owner}`.toLowerCase().includes(q));
  }, [contentFilter, contentRows]);

  return (
    <QualityAuditsSectionLayout
      title="Audit Plan / Schedule"
      subtitle="Single planning surface with calendar, list, and content modes."
    >
      <div className="qms-header__actions">
        <div className="qms-segmented" role="tablist" aria-label="Planner view mode">
          {([
            ["calendar", "Calendar view"],
            ["list", "List view"],
            ["content", "Content view"],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={view === key}
              className={view === key ? "is-active" : ""}
              onClick={() => setView(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits`)}>
          Back to Audits
        </button>
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

      {view === "calendar" && (
        <div className="qms-grid">
          {groupedCalendar.length === 0 ? (
            <EmptyState title="No schedules" description="Create schedules to populate the planner calendar." />
          ) : (
            groupedCalendar.map(([date, rows]) => (
              <section key={date} className="qms-card">
                <h3 style={{ marginTop: 0 }}>{date}</h3>
                {rows.map((schedule) => (
                  <button
                    type="button"
                    key={schedule.id}
                    className="qms-action-list__row"
                    onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/${schedule.id}`)}
                  >
                    <span>{schedule.title}</span>
                    <span>{schedule.frequency}</span>
                  </button>
                ))}
              </section>
            ))
          )}
        </div>
      )}

      {view === "list" && (
        <DataTableShell title="Schedule list">
          <table className={`table ${density === "compact" ? "table-row--compact" : "table-row--comfortable"} ${wrapText ? "table--wrap" : ""}`}>
            <thead>
              <tr>
                <th>Title</th>
                <th>Frequency</th>
                <th>Next due</th>
                {showOwnerColumn ? <th>Lead auditor</th> : null}
              </tr>
              {showFilters ? (
                <tr>
                  <th><input className="input" style={{ height: 30 }} placeholder="Filter title" value={listFilter.title} onChange={(e) => setListFilter((prev) => ({ ...prev, title: e.target.value }))} /></th>
                  <th><input className="input" style={{ height: 30 }} placeholder="Frequency" value={listFilter.frequency} onChange={(e) => setListFilter((prev) => ({ ...prev, frequency: e.target.value }))} /></th>
                  <th></th>
                  {showOwnerColumn ? <th><input className="input" style={{ height: 30 }} placeholder="Owner" value={listFilter.owner} onChange={(e) => setListFilter((prev) => ({ ...prev, owner: e.target.value }))} /></th> : null}
                </tr>
              ) : null}
            </thead>
            <tbody>
              {filteredSchedules.map((schedule) => (
                <tr key={schedule.id} onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/${schedule.id}`)} style={{ cursor: "pointer" }}>
                  <td>{schedule.title}</td>
                  <td>{schedule.frequency}</td>
                  <td>{schedule.next_due_date}</td>
                  {showOwnerColumn ? <td>{schedule.lead_auditor_user_id ?? "Unassigned"}</td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </DataTableShell>
      )}

      {view === "content" && (
        <DataTableShell title="Content view" actions={<input className="input" style={{ height: 34, maxWidth: 280 }} placeholder="Quick filter" value={contentFilter} onChange={(e) => setContentFilter(e.target.value)} />}>
          <table className={`table ${density === "compact" ? "table-row--compact" : "table-row--comfortable"} ${wrapText ? "table--wrap" : ""}`}>
            <thead>
              <tr>
                <th>Type</th>
                <th>Title</th>
                <th>Status</th>
                <th>Date</th>
                <th>Owner</th>
                <th>Quick action</th>
              </tr>
            </thead>
            <tbody>
              {filteredContentRows.map((row) => (
                <tr key={row.id}>
                  <td>{row.kind}</td>
                  <td>{row.title}</td>
                  <td>{row.status}</td>
                  <td>{row.date}</td>
                  <td>{row.owner}</td>
                  <td>
                    <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/${row.id}`)}>
                      Open schedule
                    </button>
                  </td>
                </tr>
              ))}
              {(auditsQuery.data ?? []).slice(0, 5).map((audit) => (
                <tr key={`audit-${audit.id}`}>
                  <td>audit</td>
                  <td>{audit.title}</td>
                  <td>{audit.status}</td>
                  <td>{audit.planned_start ?? "—"}</td>
                  <td>{audit.lead_auditor_user_id ?? "Unassigned"}</td>
                  <td>
                    <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/${audit.id}`)}>
                      Open audit run hub
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataTableShell>
      )}
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditPlanSchedulePage;
