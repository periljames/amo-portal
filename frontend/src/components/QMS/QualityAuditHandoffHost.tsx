import React, { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarPlus, CheckCircle2, PanelRightClose, PanelRightOpen, ShieldAlert } from "lucide-react";

import {
  createAuditHandoff,
  getPlannerHandoffOptions,
  listMissionHandoffSources,
  listSignalHandoffSources,
  type AuditHandoffSource,
} from "../../services/qmsAuditHandoff";
import "../../styles/qms-audit-handoff.css";

type Props = { amoCode?: string };

type Workspace = "missions" | "intelligence" | null;

function workspaceFromLocation(pathname: string, search: string): Workspace {
  const query = new URLSearchParams(search).get("workspace")?.toLowerCase();
  if (query === "missions" || query === "intelligence") return query;
  if (/\/quality\/missions(?:\/|$)/i.test(pathname)) return "missions";
  if (/\/quality\/intelligence(?:\/|$)/i.test(pathname)) return "intelligence";
  return null;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Audit handoff could not be created.";
}

const QualityAuditHandoffHost: React.FC<Props> = ({ amoCode = "" }) => {
  const location = useLocation();
  const workspace = workspaceFromLocation(location.pathname, location.search);
  const pathnameAmo = location.pathname.match(/^\/maintenance\/([^/]+)\//i)?.[1];
  const resolvedAmo = amoCode || (pathnameAmo ? decodeURIComponent(pathnameAmo) : "");
  const [open, setOpen] = useState(false);
  const [sourceId, setSourceId] = useState("");
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("09:00");
  const [locationText, setLocationText] = useState("");
  const [scope, setScope] = useState("");
  const [criteria, setCriteria] = useState("");
  const [leadAuditor, setLeadAuditor] = useState("");
  const [rationale, setRationale] = useState("Source-backed targeted assurance requirement.");
  const [success, setSuccess] = useState<{ id: string; title: string; next_due_date: string } | null>(null);
  const [error, setError] = useState("");

  const sourceQuery = useQuery({
    queryKey: ["qms-audit-handoff-sources", resolvedAmo, workspace],
    queryFn: ({ signal }) => workspace === "missions" ? listMissionHandoffSources(resolvedAmo, signal) : listSignalHandoffSources(resolvedAmo, signal),
    enabled: Boolean(open && resolvedAmo && workspace),
  });
  const optionsQuery = useQuery({
    queryKey: ["qms-audit-handoff-options", resolvedAmo],
    queryFn: ({ signal }) => getPlannerHandoffOptions(resolvedAmo, signal),
    enabled: Boolean(open && resolvedAmo && workspace),
  });

  const sources = sourceQuery.data || [];
  const selected = useMemo<AuditHandoffSource | undefined>(() => sources.find((row) => row.id === sourceId), [sources, sourceId]);

  useEffect(() => {
    if (!sourceId && sources.length) setSourceId(sources[0].id);
  }, [sourceId, sources]);
  useEffect(() => {
    if (selected && !title) setTitle(`Targeted audit · ${selected.label}`);
  }, [selected, title]);

  const createMutation = useMutation({
    mutationFn: () => {
      if (!workspace || !sourceId) return Promise.reject(new Error("Select a governed source."));
      return createAuditHandoff(resolvedAmo, workspace === "missions" ? "MISSION" : "SIGNAL", sourceId, {
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

  if (!workspace || !resolvedAmo) return null;
  const ready = Boolean(sourceId && title.trim().length >= 3 && date && rationale.trim().length >= 8);

  return <>
    <button className="qms-audit-handoff-launcher" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="qms-audit-handoff-panel">
      {open ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />} Create audit handoff
    </button>
    {open ? <aside id="qms-audit-handoff-panel" className="qms-audit-handoff-panel" aria-label="Create governed audit handoff">
      <header><div><span>{workspace === "missions" ? "Mission" : "Intelligence"} → Planner</span><strong>Targeted audit handoff</strong></div><button type="button" onClick={() => setOpen(false)} aria-label="Close audit handoff"><PanelRightClose size={18} /></button></header>
      <div className="qms-audit-handoff-body">
        <p>The source remains authoritative in {workspace === "missions" ? "Missions" : "Intelligence"}. This action creates a guarded one-time Planner schedule and retains immutable source lineage.</p>
        {error ? <div className="qms-audit-handoff-error" role="alert"><ShieldAlert size={16} /> {error}</div> : null}
        {success ? <div className="qms-audit-handoff-success"><CheckCircle2 size={17} /><div><strong>Planner schedule created</strong><span>{success.title} · {success.next_due_date}</span><a href={`/maintenance/${encodeURIComponent(resolvedAmo)}/quality/calendar/week`}>Open Planner</a></div></div> : null}
        <label>Governed source<select value={sourceId} onChange={(event) => { setSourceId(event.target.value); setTitle(""); setSuccess(null); }}><option value="">Select source</option>{sources.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}</select></label>
        {selected?.detail ? <small>{selected.detail}</small> : null}
        <label>Audit title<input value={title} onChange={(event) => setTitle(event.target.value)} /></label>
        <div className="qms-audit-handoff-grid"><label>Date<input type="date" value={date} onChange={(event) => setDate(event.target.value)} /></label><label>Start time<input type="time" value={time} onChange={(event) => setTime(event.target.value)} /></label></div>
        <label>Lead auditor<select value={leadAuditor} onChange={(event) => setLeadAuditor(event.target.value)}><option value="">Unassigned</option>{optionsQuery.data?.people.map((person) => <option key={person.id} value={person.id}>{person.full_name}{person.role ? ` · ${person.role}` : ""}</option>)}</select></label>
        <label>Location<input value={locationText} onChange={(event) => setLocationText(event.target.value)} /></label>
        <label>Scope<textarea value={scope} onChange={(event) => setScope(event.target.value)} /></label>
        <label>Criteria<textarea value={criteria} onChange={(event) => setCriteria(event.target.value)} /></label>
        <label>Handoff rationale<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} /></label>
        <button type="button" className="qms-audit-handoff-submit" onClick={() => createMutation.mutate()} disabled={!ready || createMutation.isPending}><CalendarPlus size={16} /> {createMutation.isPending ? "Creating guarded schedule…" : "Create Planner audit"}</button>
      </div>
    </aside> : null}
  </>;
};

export default QualityAuditHandoffHost;
