import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, FileText, RefreshCw, Send, Users } from "lucide-react";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { apiRequest } from "../../../services/apiClient";
import { qmsListFindings } from "../../../services/qms";
import {
  listAuditFindingReleases,
  releaseAuditFinding,
  type AuditFindingReleaseState,
} from "../../../services/qmsAuditExternalAccess";
import {
  getAuditClosingNarrative,
  listAuditMeetings,
  updateAuditClosingNarrative,
  updateAuditMeeting,
  type AuditClosingNarrative,
} from "../../../services/qmsAuditOccurrenceCompletion";
import { resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";

type Props = { amoCode: string; auditKey: string };

type AuditCar = {
  id: string;
  car_number: string;
  title: string;
  status: string;
  finding_id: string | null;
  due_date: string | null;
  target_closure_date: string | null;
};

type AuditCarRegister = { items: AuditCar[] };

function listAuditCars(auditId: string, signal?: AbortSignal) {
  const params = new URLSearchParams({ audit_id: auditId, limit: "200", offset: "0" });
  return apiRequest<AuditCarRegister>(`/quality/cars/register?${params.toString()}`, {
    timeoutMs: 15_000,
    cacheTtlMs: 2_000,
    signal,
  });
}

const emptyNarrative: AuditClosingNarrative = {
  management_summary: null,
  conclusion: null,
  positive_practices: null,
  updated_at: null,
};

const AuditClosingNarrativePanel: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [draftOverride, setDraftOverride] = useState<AuditClosingNarrative | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: ["qms-closing-narrative-resolve", amoCode, auditKey],
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const narrativeQueryKey = ["qms-audit-closing-narrative", amoCode, auditId] as const;
  const narrativeQuery = useQuery({ queryKey: narrativeQueryKey, queryFn: ({ signal }) => getAuditClosingNarrative(amoCode, auditId, signal), enabled: Boolean(auditId), staleTime: 1_500 });
  const meetingsQuery = useQuery({ queryKey: ["qms-audit-meetings", amoCode, auditId], queryFn: ({ signal }) => listAuditMeetings(amoCode, auditId, signal), enabled: Boolean(auditId), staleTime: 2_000 });
  const findingsQuery = useQuery({ queryKey: ["qms-closing-findings", amoCode, auditId], queryFn: () => qmsListFindings(auditId), enabled: Boolean(auditId), staleTime: 2_000 });
  const carsQuery = useQuery({ queryKey: ["qms-audit-cars", amoCode, auditId], queryFn: ({ signal }) => listAuditCars(auditId, signal), enabled: Boolean(auditId), staleTime: 2_000 });
  const releasesQuery = useQuery({ queryKey: ["qms-closing-finding-releases", amoCode, auditId], queryFn: ({ signal }) => listAuditFindingReleases(amoCode, auditId, signal), enabled: Boolean(auditId), staleTime: 1_500 });
  const persistedNarrative = narrativeQuery.data ?? emptyNarrative;
  const draft = draftOverride ?? persistedNarrative;
  const updateDraft = (patch: Partial<AuditClosingNarrative>) => setDraftOverride((current) => ({ ...(current ?? persistedNarrative), ...patch }));

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-closing-narrative", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-meetings", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-closing-findings", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-cars", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-closing-finding-releases", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-report-composition", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
    ]);
  };

  const saveMutation = useMutation({
    mutationFn: () => updateAuditClosingNarrative(amoCode, auditId, {
      management_summary: draft.management_summary?.trim() || null,
      conclusion: draft.conclusion?.trim() || null,
      positive_practices: draft.positive_practices?.trim() || null,
    }),
    onSuccess: async (row) => {
      queryClient.setQueryData(narrativeQueryKey, row);
      setDraftOverride(null);
      setLocalError(null);
      setNotice("Closing narrative saved. The next generated report hash will include this exact content.");
      await refresh();
    },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Closing narrative could not be saved."),
  });

  const releaseMutation = useMutation({
    mutationFn: (findingId: string) => releaseAuditFinding(amoCode, auditId, findingId, {
      action: "RELEASED",
      include_objective_evidence: false,
      released_evidence_refs: [],
      reason: "Released to the auditee during the governed closing meeting together with its linked corrective-action obligation.",
    }),
    onSuccess: async () => { setLocalError(null); setNotice("Finding and its linked CAR are now visible through the purpose-bound auditee collaboration projection. Private auditor notes and unreleased files remain internal."); await refresh(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Finding/CAR release failed."),
  });

  const meetingMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "IN_PROGRESS" | "COMPLETED" }) => updateAuditMeeting(amoCode, auditId, id, { status }),
    onSuccess: async (row) => { setLocalError(null); setNotice(`Closing meeting is now ${row.status.replaceAll("_", " ").toLowerCase()}.`); await refresh(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Closing meeting status could not be updated."),
  });

  const closingMeeting = useMemo(() => meetingsQuery.data?.items.find((row) => row.meeting_type === "CLOSING" && row.status !== "CANCELLED") || null, [meetingsQuery.data?.items]);
  const releaseByFinding = useMemo(() => {
    const map = new Map<string, AuditFindingReleaseState>();
    for (const row of releasesQuery.data?.items || []) map.set(row.finding_id, row);
    return map;
  }, [releasesQuery.data?.items]);
  const carByFinding = useMemo(() => new Map((carsQuery.data?.items || []).filter((row) => row.finding_id).map((row) => [String(row.finding_id), row])), [carsQuery.data?.items]);
  const findings = findingsQuery.data || [];
  const narrativeReady = Boolean(draft.management_summary?.trim() && draft.conclusion?.trim() && draft.positive_practices?.trim());
  const loadError = auditQuery.error || narrativeQuery.error || meetingsQuery.error || findingsQuery.error || carsQuery.error || releasesQuery.error;

  if (auditQuery.isLoading || narrativeQuery.isLoading || meetingsQuery.isLoading || findingsQuery.isLoading || carsQuery.isLoading || releasesQuery.isLoading) return <section className="qms-occurrence-stage qms-occurrence-stage--loading">Loading closing meeting record…</section>;
  if (loadError || !auditQuery.data) return <section className="qms-occurrence-stage qms-occurrence-stage--loading" role="alert"><AlertTriangle size={18} /> {loadError instanceof Error ? loadError.message : "Closing meeting record unavailable."}</section>;

  return (
    <section className="qms-occurrence-stage qms-occurrence-stage--closing-record" aria-label="Closing meeting narrative and corrective actions">
      <header className="qms-occurrence-stage__header">
        <div><span>CLOSING · controlled meeting record</span><h2>Conclusion, positive practices and CAR release</h2><p>These fields are authoritative report inputs, not presentation-only notes.</p></div>
        <button type="button" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</button>
      </header>
      {localError ? <div className="qms-occurrence-stage__message is-error" role="alert"><AlertTriangle size={15} /> {localError}</div> : null}
      {notice ? <div className="qms-occurrence-stage__message" role="status"><CheckCircle2 size={15} /> {notice}</div> : null}

      <div className="qms-occurrence-stage__grid">
        <main>
          <article className="qms-occurrence-stage__card">
            <header><FileText size={18} /><div><strong>Governed report narrative</strong><small>All three statements must be intentionally completed before report generation.</small></div></header>
            <label><span>Management summary</span><textarea rows={5} readOnly={!canManage} value={draft.management_summary || ""} onChange={(event) => updateDraft({ management_summary: event.target.value })} placeholder="Concise management-level summary of audit purpose, coverage and outcome." /></label>
            <label><span>Audit conclusion</span><textarea rows={5} readOnly={!canManage} value={draft.conclusion || ""} onChange={(event) => updateDraft({ conclusion: event.target.value })} placeholder="Overall conformity/effectiveness conclusion supported by the fieldwork." /></label>
            <label><span>Positive practices</span><textarea rows={4} readOnly={!canManage} value={draft.positive_practices || ""} onChange={(event) => updateDraft({ positive_practices: event.target.value })} placeholder="Record observed positive practices, or explicitly state that none were noted." /></label>
            <div className="qms-occurrence-stage__actions">{canManage ? <button type="button" className="is-primary" disabled={!narrativeReady || saveMutation.isPending} onClick={() => saveMutation.mutate()}><FileText size={15} /> {saveMutation.isPending ? "Saving…" : "Save report narrative"}</button> : null}<span>{narrativeReady ? "Narrative complete" : "Narrative incomplete · report generation is blocked"}</span></div>
          </article>

          <article className="qms-occurrence-stage__card">
            <header><Send size={18} /><div><strong>Findings and corrective actions shared at closing</strong><small>Official non-conformities already create their governed CAR atomically. Closing controls whether the finding/CAR is released to the auditee.</small></div></header>
            {!findings.length ? <p>No governed findings were recorded.</p> : <div className="qms-occurrence-stage__queue">{findings.map((finding) => {
              const release = releaseByFinding.get(finding.id);
              const car = carByFinding.get(finding.id);
              const released = release?.action === "RELEASED";
              return <div className="qms-occurrence-stage__queue-row" key={finding.id}><div><strong>{finding.finding_ref || finding.level || "Finding"}</strong><span>{finding.description}</span><small>{car ? `${car.car_number} · ${car.status.replaceAll("_", " ")} · due ${car.target_closure_date || car.due_date || "not set"}` : finding.finding_type === "OBSERVATION" ? "Observation · no CAR required" : "CAR linkage unavailable — resolve before closing"}</small></div><div><em data-state={released ? "closed" : "open"}>{released ? "Shared" : "Internal"}</em>{canManage && car && !released ? <button type="button" disabled={releaseMutation.isPending} onClick={() => releaseMutation.mutate(finding.id)}><Send size={14} /> Share finding + CAR</button> : null}</div></div>;
            })}</div>}
          </article>
        </main>

        <aside>
          <article className="qms-occurrence-stage__card">
            <header><Users size={18} /><div><strong>Closing meeting</strong><small>Same occurrence meeting configured in Setup and visible to authorised auditee participants.</small></div></header>
            {closingMeeting ? <><dl><div><dt>Start</dt><dd>{new Date(closingMeeting.scheduled_start).toLocaleString()}</dd></div><div><dt>End</dt><dd>{closingMeeting.scheduled_end ? new Date(closingMeeting.scheduled_end).toLocaleString() : "—"}</dd></div><div><dt>Location</dt><dd>{closingMeeting.location || "—"}</dd></div><div><dt>Status</dt><dd>{closingMeeting.status.replaceAll("_", " ")}</dd></div></dl>{closingMeeting.agenda ? <p>{closingMeeting.agenda}</p> : null}{canManage && closingMeeting.status === "PLANNED" ? <button type="button" onClick={() => meetingMutation.mutate({ id: closingMeeting.id, status: "IN_PROGRESS" })}>Start closing meeting</button> : null}{canManage && closingMeeting.status === "IN_PROGRESS" ? <button type="button" className="is-primary" onClick={() => meetingMutation.mutate({ id: closingMeeting.id, status: "COMPLETED" })}>Record meeting complete</button> : null}</> : <div className="qms-occurrence-stage__message is-error"><AlertTriangle size={15} /> No closing meeting is configured. Return to Setup to create one.</div>}
          </article>
        </aside>
      </div>
    </section>
  );
};

export default AuditClosingNarrativePanel;