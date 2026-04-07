import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import { getContext } from "../../services/auth";
import {
  qmsCreateAuditSchedule,
  qmsListAudits,
  qmsListAuditSchedules,
  qmsRunAuditSchedule,
  type QMSAuditScheduleFrequency,
} from "../../services/qms";
import { getDueMessage } from "./dueStatus";
import { selectRelevantDueSchedule } from "../../utils/auditDate";

type PlannerView = "calendar" | "list" | "table";

const frequencies: QMSAuditScheduleFrequency[] = ["ONE_TIME", "MONTHLY", "QUARTERLY", "BI_ANNUAL", "ANNUAL"];

const defaultSchedule = {
  title: "",
  kind: "Internal Audit",
  frequency: "QUARTERLY" as QMSAuditScheduleFrequency,
  next_due_date: "",
  duration_days: "3",
  scope: "",
  criteria: "",
  auditee: "",
  auditee_email: "",
  auditee_user_id: "",
  lead_auditor_user_id: "",
  observer_auditor_user_id: "",
  assistant_auditor_user_id: "",
};

const QualityAuditPlanSchedulePage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tick, setTick] = useState(Date.now());
  const [form, setForm] = useState(defaultSchedule);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const view = (["calendar", "list", "table"].includes(searchParams.get("view") || "") ? searchParams.get("view") : "calendar") as PlannerView;

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-schedules", amoCode, department],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }),
    staleTime: 60_000,
  });

  const auditsQuery = useQuery({
    queryKey: ["qms-audits", "planner", amoCode, department],
    queryFn: () => qmsListAudits({ domain: "AMO" }),
    staleTime: 60_000,
  });

  const createSchedule = useMutation({
    mutationFn: async () => {
      const duration = Number(form.duration_days);
      if (!form.title.trim() || !form.next_due_date || !Number.isFinite(duration) || duration < 1) {
        throw new Error("Title, due date, and valid duration are required.");
      }
      return qmsCreateAuditSchedule({
        domain: "AMO",
        title: form.title.trim(),
        kind: form.kind.trim() || "Internal Audit",
        frequency: form.frequency,
        next_due_date: form.next_due_date,
        duration_days: duration,
        scope: form.scope.trim() || null,
        criteria: form.criteria.trim() || null,
        auditee: form.auditee.trim() || null,
        auditee_email: form.auditee_email.trim() || null,
        auditee_user_id: form.auditee_user_id.trim() || null,
        lead_auditor_user_id: form.lead_auditor_user_id.trim() || null,
        observer_auditor_user_id: form.observer_auditor_user_id.trim() || null,
        assistant_auditor_user_id: form.assistant_auditor_user_id.trim() || null,
      });
    },
    onSuccess: async () => {
      setError(null);
      setForm(defaultSchedule);
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode, department] });
    },
    onError: (e: Error) => setError(e.message || "Failed to create schedule."),
  });

  const runSchedule = useMutation({
    mutationFn: (scheduleId: string) => qmsRunAuditSchedule(scheduleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["qms-audits", "planner", amoCode, department] });
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode, department] });
    },
  });

  const schedules = schedulesQuery.data ?? [];
  const nearestDue = useMemo(() => selectRelevantDueSchedule(schedules, new Date(tick)), [schedules, tick]);
  const dueBanner = getDueMessage(new Date(tick), nearestDue?.next_due_date);

  return (
    <QualityAuditsSectionLayout title="Audit Planner" subtitle="Plan and schedule audits with backend-backed participant fields.">
      <div className="qms-header__actions" style={{ marginBottom: 12 }}>
        {["calendar", "list", "table"].map((v) => (
          <button key={v} type="button" className={view === v ? "btn btn-primary" : "secondary-chip-btn"} onClick={() => setSearchParams({ view: v })}>
            {v}
          </button>
        ))}
      </div>

      {dueBanner && nearestDue ? <div className="qms-card" style={{ marginBottom: 12 }}><strong>{dueBanner.label}</strong> · {nearestDue.title} ({nearestDue.next_due_date})</div> : null}

      <div className="qms-card" style={{ marginBottom: 12 }}>
        <h3 style={{ marginTop: 0 }}>Create Schedule</h3>
        <div className="qms-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          {Object.entries(form).map(([k, v]) => (
            <label key={k} className="qms-field">
              {k}
              {k === "frequency" ? (
                <select value={form.frequency} onChange={(e) => setForm((p) => ({ ...p, frequency: e.target.value as QMSAuditScheduleFrequency }))}>
                  {frequencies.map((freq) => <option key={freq} value={freq}>{freq}</option>)}
                </select>
              ) : k === "next_due_date" ? (
                <input type="date" value={String(v)} onChange={(e) => setForm((p) => ({ ...p, [k]: e.target.value }))} />
              ) : (
                <input value={String(v)} onChange={(e) => setForm((p) => ({ ...p, [k]: e.target.value }))} />
              )}
            </label>
          ))}
        </div>
        <div className="qms-header__actions">
          <button type="button" className="btn btn-primary" onClick={() => createSchedule.mutate()} disabled={createSchedule.isPending}>Create</button>
          {error ? <span className="text-danger">{error}</span> : null}
        </div>
      </div>

      <div className="qms-card">
        <h3 style={{ marginTop: 0 }}>{view === "table" ? "Table" : view === "list" ? "List" : "Calendar"} view</h3>
        <table className="table">
          <thead><tr><th>Title</th><th>Frequency</th><th>Due</th><th>Auditee</th><th>Lead</th><th>Run</th><th>Open</th></tr></thead>
          <tbody>
            {schedules.map((s) => (
              <tr key={s.id}>
                <td>{s.title}</td><td>{s.frequency}</td><td>{s.next_due_date}</td><td>{s.auditee || "—"}</td><td>{s.lead_auditor_user_id || "—"}</td>
                <td><button type="button" className="secondary-chip-btn" onClick={() => runSchedule.mutate(s.id)}>Run</button></td>
                <td><button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/${s.id}`)}>Detail</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="qms-card" style={{ marginTop: 12 }}>
        <h3 style={{ marginTop: 0 }}>Audit timeline</h3>
        <ul>
          {(auditsQuery.data ?? []).filter((a) => a.planned_start).map((a) => <li key={a.id}>{a.audit_ref} · {a.planned_start} → {a.planned_end || "—"}</li>)}
        </ul>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditPlanSchedulePage;
