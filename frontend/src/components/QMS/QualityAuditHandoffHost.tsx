import React, { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarPlus, CheckCircle2, ShieldAlert } from "lucide-react";

import {
  createAuditHandoff,
  getPlannerHandoffOptions,
} from "../../services/qmsAuditHandoff";
import "../../styles/qms-audit-handoff.css";
import { hasQmsRolePermission } from "../../app/routeGuards";

type Props = { amoCode: string; sourceType: "MISSION" | "SIGNAL"; sourceId: string; sourceLabel: string };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Audit handoff could not be created.";
}

const QualityAuditHandoffHost: React.FC<Props> = ({ amoCode: resolvedAmo, sourceType, sourceId, sourceLabel }) => {
  const canSchedule = hasQmsRolePermission("qms.audit.manage");
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(`Targeted audit - ${sourceLabel}`);
  const [date, setDate] = useState("");
  const [time, setTime] = useState("09:00");
  const [locationText, setLocationText] = useState("");
  const [scope, setScope] = useState("");
  const [criteria, setCriteria] = useState("");
  const [leadAuditor, setLeadAuditor] = useState("");
  const [rationale, setRationale] = useState("");
  const [success, setSuccess] = useState<{ id: string; title: string; next_due_date: string } | null>(null);
  const [error, setError] = useState("");

  const optionsQuery = useQuery({
    queryKey: ["qms-audit-handoff-options", resolvedAmo],
    queryFn: ({ signal }) => getPlannerHandoffOptions(resolvedAmo, signal),
    enabled: Boolean(open && resolvedAmo && canSchedule),
  });

  const createMutation = useMutation({
    mutationFn: () => {
      if (!canSchedule || !sourceId) return Promise.reject(new Error("Select a governed source."));
      return createAuditHandoff(resolvedAmo, sourceType, sourceId, {
        rationale,
        schedule: {
          title,
          next_due_date: date,
          start_time: time,
          duration_days: 1,
          location: locationText || undefined,
          scope: scope || undefined,
          criteria: criteria || undefined,
          lead_auditor_user_id: leadAuditor || undefined,
          frequency: "ONE_TIME",
          timezone_name: optionsQuery.data?.timezone_name || "Africa/Nairobi",
          allow_conflicts: false,
        },
      });
    },
    onSuccess: (row) => {
      setError("");
      setSuccess(row);
    },
    onError: (cause) => setError(errorMessage(cause)),
  });

  if (!canSchedule || !resolvedAmo) return null;
  const ready = Boolean(sourceId && title.trim().length >= 3 && date && rationale.trim().length >= 8);

  return <details className="qms-audit-handoff-inline" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>Schedule a targeted audit for this {sourceType === "MISSION" ? "change" : "signal"}</summary>
    {open ? <section className="qms-audit-handoff-panel" aria-label="Schedule source-linked audit">
      <header><div><strong>{sourceLabel}</strong><span>Creates an audit in the existing Planner</span></div></header>
      <div className="qms-audit-handoff-body">
        <p>The source remains authoritative in {sourceType === "MISSION" ? "Missions" : "Intelligence"}. This action creates a guarded one-time Planner schedule and retains immutable source lineage.</p>
        {error ? <div className="qms-audit-handoff-error" role="alert"><ShieldAlert size={16} /> {error}</div> : null}
        {success ? <div className="qms-audit-handoff-success"><CheckCircle2 size={17} /><div><strong>Planner schedule created</strong><span>{success.title} · {success.next_due_date}</span><a href={`/maintenance/${encodeURIComponent(resolvedAmo)}/quality/calendar/week`}>Open Planner</a></div></div> : null}
        {optionsQuery.error ? <p role="alert">{errorMessage(optionsQuery.error)}</p> : null}
        <fieldset disabled={createMutation.isPending || Boolean(success)}>
        <label>Audit title<input value={title} onChange={(event) => setTitle(event.target.value)} /></label>
        <div className="qms-audit-handoff-grid"><label>Date<input type="date" value={date} onChange={(event) => setDate(event.target.value)} /></label><label>Start time<input type="time" value={time} onChange={(event) => setTime(event.target.value)} /></label></div>
        <label>Lead auditor<select value={leadAuditor} onChange={(event) => setLeadAuditor(event.target.value)}><option value="">Unassigned</option>{optionsQuery.data?.people.map((person) => <option key={person.id} value={person.id}>{person.full_name}{person.role ? ` · ${person.role}` : ""}</option>)}</select></label>
        <label>Location<input value={locationText} onChange={(event) => setLocationText(event.target.value)} /></label>
        <label>Scope<textarea value={scope} onChange={(event) => setScope(event.target.value)} /></label>
        <label>Criteria<textarea value={criteria} onChange={(event) => setCriteria(event.target.value)} /></label>
        <label>Handoff rationale<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} /></label>
        <button type="button" className="qms-audit-handoff-submit" onClick={() => createMutation.mutate()} disabled={!ready || createMutation.isPending}><CalendarPlus size={16} /> {createMutation.isPending ? "Creating guarded schedule…" : "Create Planner audit"}</button>
        </fieldset>
      </div>
    </section> : null}
  </details>;
};

export default QualityAuditHandoffHost;
