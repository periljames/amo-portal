import React, { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, CheckCircle2, History, PanelRightClose, PanelRightOpen, ShieldAlert, Zap } from "lucide-react";

import {
  createProgrammeOccurrence,
  getOccurrencePlannerOptions,
  getOccurrenceProgramme,
  listOccurrenceProgrammes,
  listOccurrenceSignals,
  listProgrammeOccurrenceLinks,
  type ProgrammeOccurrenceItem,
} from "../../services/qmsProgrammeOccurrences";
import "../../styles/qms-programme-occurrences.css";

type Props = { amoCode?: string };

type OccurrenceType = "CUSTOM" | "RISK_TRIGGERED";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The governed programme occurrence could not be created.";
}

function recurrenceItemLabel(item: ProgrammeOccurrenceItem): string {
  return item.universe_item?.display_label || item.rationale || `Programme requirement ${item.id.slice(0, 8)}`;
}

const QualityProgrammeOccurrenceHost: React.FC<Props> = ({ amoCode = "" }) => {
  const location = useLocation();
  const isProgrammeRoute = /\/quality\/audits\/program(?:\/|$)/i.test(location.pathname)
    || /\/qms\/audits\/program(?:\/|$)/i.test(location.pathname);
  const pathnameAmo = location.pathname.match(/^\/maintenance\/([^/]+)\//i)?.[1];
  const resolvedAmo = amoCode || (pathnameAmo ? decodeURIComponent(pathnameAmo) : "");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [programmeId, setProgrammeId] = useState("");
  const [itemId, setItemId] = useState("");
  const [occurrenceKey, setOccurrenceKey] = useState("");
  const [signalId, setSignalId] = useState("");
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("09:00");
  const [leadAuditor, setLeadAuditor] = useState("");
  const [locationText, setLocationText] = useState("");
  const [scope, setScope] = useState("");
  const [criteria, setCriteria] = useState("");
  const [rationale, setRationale] = useState("Controlled programme occurrence requiring authoritative Planner scheduling.");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<{ id: string; title: string; next_due_date: string } | null>(null);

  const programmesQuery = useQuery({
    queryKey: ["qms-occurrence-programmes", resolvedAmo],
    queryFn: ({ signal }) => listOccurrenceProgrammes(resolvedAmo, signal),
    enabled: Boolean(open && isProgrammeRoute && resolvedAmo),
  });
  const programmeQuery = useQuery({
    queryKey: ["qms-occurrence-programme", resolvedAmo, programmeId],
    queryFn: ({ signal }) => getOccurrenceProgramme(resolvedAmo, programmeId, signal),
    enabled: Boolean(open && programmeId),
  });
  const linksQuery = useQuery({
    queryKey: ["qms-programme-occurrence-links", resolvedAmo, programmeId],
    queryFn: ({ signal }) => listProgrammeOccurrenceLinks(resolvedAmo, programmeId, signal),
    enabled: Boolean(open && programmeId),
  });
  const signalsQuery = useQuery({
    queryKey: ["qms-occurrence-signals", resolvedAmo],
    queryFn: ({ signal }) => listOccurrenceSignals(resolvedAmo, signal),
    enabled: Boolean(open && resolvedAmo),
  });
  const optionsQuery = useQuery({
    queryKey: ["qms-occurrence-planner-options", resolvedAmo],
    queryFn: ({ signal }) => getOccurrencePlannerOptions(resolvedAmo, signal),
    enabled: Boolean(open && resolvedAmo),
  });

  const programmes = useMemo(
    () => (programmesQuery.data?.items || []).filter((row) => row.status === "APPROVED" || row.status === "ACTIVE"),
    [programmesQuery.data?.items],
  );
  const recurrenceItems = useMemo(
    () => (programmeQuery.data?.items || []).filter((item) => item.recurrence === "CUSTOM" || item.recurrence === "RISK_TRIGGERED"),
    [programmeQuery.data?.items],
  );
  const selectedItem = recurrenceItems.find((item) => item.id === itemId);
  const occurrenceType = selectedItem?.recurrence as OccurrenceType | undefined;
  const links = linksQuery.data?.items || [];

  useEffect(() => {
    if (!programmeId && programmes.length) setProgrammeId(programmes[0].id);
  }, [programmeId, programmes]);
  useEffect(() => {
    if (programmeId) {
      setItemId("");
      setSuccess(null);
    }
  }, [programmeId]);
  useEffect(() => {
    if (!itemId && recurrenceItems.length) setItemId(recurrenceItems[0].id);
  }, [itemId, recurrenceItems]);
  useEffect(() => {
    if (!selectedItem) return;
    const label = recurrenceItemLabel(selectedItem);
    setTitle(`Programme audit · ${label}`);
    if (!date) setDate(selectedItem.target_start || "");
    setOccurrenceKey(`${selectedItem.recurrence.toLowerCase()}-${selectedItem.id.slice(0, 8)}-${selectedItem.target_start || "occurrence"}`);
    setSignalId("");
    setSuccess(null);
  }, [selectedItem]); // eslint-disable-line react-hooks/exhaustive-deps

  const mutation = useMutation({
    mutationFn: () => {
      if (!selectedItem || !occurrenceType) return Promise.reject(new Error("Select a CUSTOM or RISK_TRIGGERED programme requirement."));
      return createProgrammeOccurrence(resolvedAmo, programmeId, selectedItem.id, occurrenceType, {
        occurrence_key: occurrenceKey,
        rationale,
        signal_id: occurrenceType === "RISK_TRIGGERED" ? signalId : undefined,
        schedule: {
          title,
          next_due_date: date,
          start_time: time,
          duration_days: 1,
          timezone_name: optionsQuery.data?.timezone_name || "Africa/Nairobi",
          location: locationText || undefined,
          scope: scope || undefined,
          criteria: criteria || undefined,
          lead_auditor_user_id: leadAuditor || undefined,
          frequency: "ONE_TIME",
          allow_conflicts: false,
        },
      });
    },
    onSuccess: async (row) => {
      setError("");
      setSuccess(row);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["qms-programme-occurrence-links", resolvedAmo, programmeId] }),
        queryClient.invalidateQueries({ queryKey: ["qms-occurrence-programme", resolvedAmo, programmeId] }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-programme"] }),
        queryClient.invalidateQueries({ queryKey: ["qms-planner"] }),
      ]);
    },
    onError: (cause) => setError(errorMessage(cause)),
  });

  if (!isProgrammeRoute || !resolvedAmo) return null;
  const ready = Boolean(
    programmeId && selectedItem && occurrenceType && occurrenceKey.trim().length >= 3 && title.trim().length >= 3
      && date && rationale.trim().length >= 8 && (occurrenceType !== "RISK_TRIGGERED" || signalId),
  );

  return <>
    <button className="qms-programme-occurrence-launcher" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="qms-programme-occurrence-panel">
      {open ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />} Custom occurrences
    </button>
    {open ? <aside id="qms-programme-occurrence-panel" className="qms-programme-occurrence-panel" aria-label="Custom and risk-triggered programme occurrences">
      <header><div><span>Audit Programme → Planner</span><strong>Custom & risk-triggered occurrences</strong></div><button type="button" onClick={() => setOpen(false)} aria-label="Close custom occurrence panel"><PanelRightClose size={18} /></button></header>
      <div className="qms-programme-occurrence-body">
        <p>CUSTOM and RISK_TRIGGERED requirements generate guarded ONE_TIME Planner schedules. The Programme retains immutable occurrence lineage; Planner remains the scheduling authority.</p>
        {error ? <div className="qms-programme-occurrence-error" role="alert"><ShieldAlert size={16} /> {error}</div> : null}
        {success ? <div className="qms-programme-occurrence-success"><CheckCircle2 size={17} /><div><strong>Occurrence linked to Planner</strong><span>{success.title} · {success.next_due_date}</span><a href={`/maintenance/${encodeURIComponent(resolvedAmo)}/quality/calendar/week`}>Open Planner</a></div></div> : null}

        <label>Programme<select value={programmeId} onChange={(event) => setProgrammeId(event.target.value)}><option value="">Select approved programme</option>{programmes.map((programme) => <option key={programme.id} value={programme.id}>{programme.programme_ref} · {programme.title}</option>)}</select></label>
        <label>Requirement<select value={itemId} onChange={(event) => setItemId(event.target.value)}><option value="">Select custom requirement</option>{recurrenceItems.map((item) => <option key={item.id} value={item.id}>{item.recurrence} · {recurrenceItemLabel(item)}</option>)}</select></label>
        {selectedItem ? <div className="qms-programme-occurrence-source"><strong>{occurrenceType}</strong><span>{selectedItem.universe_item?.source_owner_module || "Audit Universe"} · {selectedItem.universe_item?.risk_classification || "UNCLASSIFIED"} risk · {selectedItem.universe_item?.regulatory_criticality || "UNCLASSIFIED"} regulatory criticality</span><small>Target window {selectedItem.target_start || "open"} → {selectedItem.target_end || selectedItem.target_start || "open"}</small></div> : null}

        {occurrenceType === "RISK_TRIGGERED" ? <label>Triggered signal<select value={signalId} onChange={(event) => setSignalId(event.target.value)}><option value="">Select open triggered signal</option>{signalsQuery.data?.items.filter((row) => row.triggered && row.state !== "CLOSED").map((row) => <option key={row.id} value={row.id}>{row.rule_code || row.metric} · {row.severity}</option>)}</select></label> : null}
        <label>Occurrence key<input value={occurrenceKey} onChange={(event) => setOccurrenceKey(event.target.value)} /></label>
        <label>Audit title<input value={title} onChange={(event) => setTitle(event.target.value)} /></label>
        <div className="qms-programme-occurrence-grid"><label>Date<input type="date" value={date} min={selectedItem?.target_start || undefined} max={selectedItem?.target_end || undefined} onChange={(event) => setDate(event.target.value)} /></label><label>Start time<input type="time" value={time} onChange={(event) => setTime(event.target.value)} /></label></div>
        <label>Lead auditor<select value={leadAuditor} onChange={(event) => setLeadAuditor(event.target.value)}><option value="">Unassigned</option>{optionsQuery.data?.people.map((person) => <option key={person.id} value={person.id}>{person.full_name}{person.role ? ` · ${person.role}` : ""}</option>)}</select></label>
        <label>Location<input value={locationText} onChange={(event) => setLocationText(event.target.value)} /></label>
        <label>Scope<textarea value={scope} onChange={(event) => setScope(event.target.value)} /></label>
        <label>Criteria<textarea value={criteria} onChange={(event) => setCriteria(event.target.value)} /></label>
        <label>Occurrence rationale<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} /></label>
        <button type="button" className="qms-programme-occurrence-submit" onClick={() => mutation.mutate()} disabled={!ready || mutation.isPending}><CalendarPlus size={16} /> {mutation.isPending ? "Creating guarded occurrence…" : "Create Planner occurrence"}</button>

        <section className="qms-programme-occurrence-history"><header><History size={17} /><strong>Occurrence lineage</strong></header>{links.length ? <ol>{links.map((link) => <li key={link.id}><strong>{link.occurrence_type} · {link.occurrence_key}</strong><span>{link.lifecycle_status || "Planner schedule"} · {new Date(link.created_at).toLocaleString()}</span><small>{link.rationale}</small></li>)}</ol> : <p>No custom/risk-triggered occurrences have been linked for this programme.</p>}</section>
      </div>
    </aside> : null}
  </>;
};

export default QualityProgrammeOccurrenceHost;
