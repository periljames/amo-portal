import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import QMSLayout from "../components/QMS/QMSLayout";
import EmptyState from "../components/shared/EmptyState";
import { getContext } from "../services/auth";
import { qmsListAuditSchedules } from "../services/qms";

const QualityAuditPlannerCalendarPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [draftDates, setDraftDates] = useState<Record<string, string>>({});

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-schedules", amoCode],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }),
    staleTime: 60_000,
  });

  const grouped = useMemo(() => {
    const groups = new Map<string, typeof schedulesQuery.data>();
    (schedulesQuery.data ?? []).forEach((item) => {
      const date = draftDates[item.id] ?? item.next_due_date;
      const bucket = groups.get(date) ?? [];
      bucket.push(item);
      groups.set(date, bucket);
    });
    return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [draftDates, schedulesQuery.data]);

  const moveSchedule = (scheduleId: string, date: string) => {
    setDraftDates((prev) => ({ ...prev, [scheduleId]: date }));
    setDraggingId(null);
  };

  return (
    <QMSLayout amoCode={amoCode} department="quality" title="Audit Planner · Calendar" subtitle="Drag-drop for planning previews, assignment checks, and conflict warnings.">
      <div className="qms-header__actions">
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/schedules/list`)}>List view</button>
      </div>
      {!grouped.length ? <EmptyState title="No schedules" description="No active schedules exist yet." action={<button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/schedules/list`)}>Open schedule list</button>} /> : null}
      <div className="qms-grid">
        {grouped.map(([date, items]) => (
          <section key={date} className="qms-card" onDragOver={(e) => e.preventDefault()} onDrop={() => draggingId && moveSchedule(draggingId, date)}>
            <h3 style={{ marginTop: 0 }}>{date}</h3>
            {(items ?? []).map((item) => {
              const auditor = item.lead_auditor_user_id ?? "Unassigned";
              const isConflict = (items ?? []).filter((row) => (draftDates[row.id] ?? row.next_due_date) === date && (row.lead_auditor_user_id ?? "") === (item.lead_auditor_user_id ?? "")).length > 1 && !!item.lead_auditor_user_id;
              return (
                <article key={item.id} draggable onDragStart={() => setDraggingId(item.id)} className="qms-dashboard-card" style={{ marginBottom: 8 }}>
                  <strong>{item.title}</strong>
                  <p style={{ margin: "4px 0" }}>{item.scope || "No scope summary provided"}</p>
                  <small>Auditor: {auditor}</small>
                  {isConflict ? <div className="badge badge--warning" style={{ marginTop: 6 }}>Conflict warning: auditor double-booked</div> : null}
                  <div style={{ marginTop: 8 }}>
                    <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/schedules/${item.id}`)}>Open</button>
                  </div>
                </article>
              );
            })}
          </section>
        ))}
      </div>
    </QMSLayout>
  );
};

export default QualityAuditPlannerCalendarPage;
