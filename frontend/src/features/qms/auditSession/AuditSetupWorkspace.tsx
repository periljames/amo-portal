import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BellRing, CalendarClock, CheckCircle2, ClipboardList, RefreshCw, Save, Send, Users, Video } from "lucide-react";
import { Link } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import {
  qmsListAuditPersonnelOptions,
  qmsResolveAudit,
  qmsUpdateAudit,
  type QMSAuditOut,
} from "../../../services/qms";
import {
  createAuditNotice,
  listAuditNotices,
  listAuditNoticePolicies,
  transitionAuditNotice,
  type AuditNotice,
} from "../../../services/qmsAuditGovernance";
import {
  createAuditMeeting,
  listAuditMeetings,
  updateAuditMeeting,
  type AuditMeeting,
} from "../../../services/qmsAuditOccurrenceCompletion";
import { getAuditSession } from "../../../services/qmsAuditSession";
import { auditSessionPath } from "./auditSessionRoutes";

type Props = { amoCode: string; auditKey: string };

type SetupDraft = {
  title: string;
  scope: string;
  criteria: string;
  auditee: string;
  auditeeEmail: string;
  plannedStart: string;
  plannedEnd: string;
  leadAuditorUserId: string;
  observerAuditorUserId: string;
  assistantAuditorUserId: string;
  notifyAuditors: boolean;
  notifyAuditees: boolean;
  reminderIntervalDays: string;
};

type MeetingDraft = {
  start: string;
  end: string;
  location: string;
  conferenceUrl: string;
  agenda: string;
};

const emptyMeeting: MeetingDraft = { start: "", end: "", location: "", conferenceUrl: "", agenda: "" };

function draftFromAudit(audit: QMSAuditOut): SetupDraft {
  return {
    title: audit.title || "",
    scope: audit.scope || "",
    criteria: audit.criteria || "",
    auditee: audit.auditee || "",
    auditeeEmail: audit.auditee_email || "",
    plannedStart: audit.planned_start || "",
    plannedEnd: audit.planned_end || "",
    leadAuditorUserId: audit.lead_auditor_user_id || "",
    observerAuditorUserId: audit.observer_auditor_user_id || "",
    assistantAuditorUserId: audit.assistant_auditor_user_id || "",
    notifyAuditors: audit.notify_auditors !== false,
    notifyAuditees: audit.notify_auditees !== false,
    reminderIntervalDays: String(audit.reminder_interval_days || 7),
  };
}

function localDateTime(value?: string | null): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const adjusted = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60_000);
  return adjusted.toISOString().slice(0, 16);
}

function meetingDraft(row: AuditMeeting | null): MeetingDraft {
  return row ? {
    start: localDateTime(row.scheduled_start),
    end: localDateTime(row.scheduled_end),
    location: row.location || "",
    conferenceUrl: row.conference_url || "",
    agenda: row.agenda || "",
  } : emptyMeeting;
}

function noticeNextAction(notice: AuditNotice): "SUBMIT" | "APPROVE" | "GENERATE" | "DELIVER" | "ACKNOWLEDGE" | null {
  if (notice.status === "DRAFT") return "SUBMIT";
  if (notice.status === "UNDER_REVIEW") return "APPROVE";
  if (notice.status === "APPROVED") return "GENERATE";
  if (notice.status === "GENERATED") return "DELIVER";
  if (notice.status === "DELIVERED") return "ACKNOWLEDGE";
  return null;
}

const AuditSetupWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [draft, setDraft] = useState<SetupDraft | null>(null);
  const [openingDraft, setOpeningDraft] = useState<MeetingDraft>(emptyMeeting);
  const [closingDraft, setClosingDraft] = useState<MeetingDraft>(emptyMeeting);
  const [noticeReason, setNoticeReason] = useState("Governed audit notice created from the current occurrence setup.");
  const [deliveryReference, setDeliveryReference] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const auditQuery = useQuery({ queryKey: ["qms-setup-audit-resolve", auditKey], queryFn: () => qmsResolveAudit(auditKey), staleTime: 5_000 });
  const auditId = auditQuery.data?.id || "";
  const personnelQuery = useQuery({ queryKey: ["qms-audit-personnel-options", amoCode], queryFn: () => qmsListAuditPersonnelOptions({ limit: 200 }), enabled: canManage, staleTime: 30_000 });
  const noticesQuery = useQuery({ queryKey: ["qms-audit-notices", amoCode, auditId], queryFn: ({ signal }) => listAuditNotices(amoCode, auditId, signal), enabled: Boolean(auditId), staleTime: 2_000 });
  const policiesQuery = useQuery({ queryKey: ["qms-audit-notice-policies", amoCode], queryFn: ({ signal }) => listAuditNoticePolicies(amoCode, signal), enabled: Boolean(auditId), staleTime: 30_000 });
  const meetingsQuery = useQuery({ queryKey: ["qms-audit-meetings", amoCode, auditId], queryFn: ({ signal }) => listAuditMeetings(amoCode, auditId, signal), enabled: Boolean(auditId), staleTime: 2_000 });
  const sessionQuery = useQuery({ queryKey: ["qms-audit-session", amoCode, auditId], queryFn: ({ signal }) => getAuditSession(amoCode, auditId, signal), enabled: Boolean(auditId), staleTime: 2_000 });

  const openingMeeting = useMemo(() => meetingsQuery.data?.items.find((row) => row.meeting_type === "OPENING" && row.status !== "CANCELLED") || null, [meetingsQuery.data?.items]);
  const closingMeeting = useMemo(() => meetingsQuery.data?.items.find((row) => row.meeting_type === "CLOSING" && row.status !== "CANCELLED") || null, [meetingsQuery.data?.items]);

  useEffect(() => { if (auditQuery.data) setDraft(draftFromAudit(auditQuery.data)); }, [auditQuery.data]);
  useEffect(() => { setOpeningDraft(meetingDraft(openingMeeting)); }, [openingMeeting]);
  useEffect(() => { setClosingDraft(meetingDraft(closingMeeting)); }, [closingMeeting]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-setup-audit-resolve", auditKey] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-notices", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-meetings", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session-resolve", auditKey] }),
    ]);
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!draft || !auditId) throw new Error("Audit occurrence is not ready for setup changes.");
      return qmsUpdateAudit(auditId, {
        title: draft.title.trim(), scope: draft.scope.trim() || null, criteria: draft.criteria.trim() || null,
        auditee: draft.auditee.trim() || null, auditee_email: draft.auditeeEmail.trim() || null,
        planned_start: draft.plannedStart || null, planned_end: draft.plannedEnd || null,
        lead_auditor_user_id: draft.leadAuditorUserId || null, observer_auditor_user_id: draft.observerAuditorUserId || null,
        assistant_auditor_user_id: draft.assistantAuditorUserId || null, notify_auditors: draft.notifyAuditors,
        notify_auditees: draft.notifyAuditees, reminder_interval_days: Math.max(1, Number(draft.reminderIntervalDays) || 7),
      });
    },
    onSuccess: async (row) => { setDraft(draftFromAudit(row)); setLocalError(null); setNotice("Audit setup saved to the authoritative occurrence."); await refresh(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Audit setup could not be saved."),
  });

  const meetingMutation = useMutation({
    mutationFn: async ({ type, row, value }: { type: "OPENING" | "CLOSING"; row: AuditMeeting | null; value: MeetingDraft }) => {
      if (!value.start) throw new Error(`${type === "OPENING" ? "Opening" : "Closing"} meeting start is required.`);
      const payload = {
        meeting_type: type,
        scheduled_start: new Date(value.start).toISOString(),
        scheduled_end: value.end ? new Date(value.end).toISOString() : null,
        location: value.location.trim() || null,
        conference_url: value.conferenceUrl.trim() || null,
        agenda: value.agenda.trim() || null,
        status: row?.status || "PLANNED" as const,
      };
      return row ? updateAuditMeeting(amoCode, auditId, row.id, payload) : createAuditMeeting(amoCode, auditId, payload);
    },
    onSuccess: async (row) => { setLocalError(null); setNotice(`${row.meeting_type.toLowerCase()} meeting saved and available to authorised participants.`); await refresh(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Audit meeting could not be saved."),
  });

  const createNoticeMutation = useMutation({
    mutationFn: async () => {
      if (!auditQuery.data || !draft) throw new Error("Save the audit occurrence before creating its notice.");
      const policy = policiesQuery.data?.items.find((item) => !item.audit_kind || item.audit_kind === auditQuery.data?.kind) || policiesQuery.data?.items[0];
      return createAuditNotice(amoCode, auditId, {
        policy_id: policy?.id,
        notice_date: new Date().toISOString().slice(0, 10),
        subject: `${auditQuery.data.audit_ref} · ${draft.title}`,
        body: `Audit scope: ${draft.scope || "Not specified"}\nCriteria: ${draft.criteria || "Not specified"}\nPlanned: ${draft.plannedStart || "TBC"} to ${draft.plannedEnd || "TBC"}`,
        reason: noticeReason.trim(),
      });
    },
    onSuccess: async () => { setLocalError(null); setNotice("Governed audit notice draft created from this occurrence."); await refresh(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Audit notice could not be created."),
  });

  const transitionNoticeMutation = useMutation({
    mutationFn: ({ row, action }: { row: AuditNotice; action: NonNullable<ReturnType<typeof noticeNextAction>> }) => transitionAuditNotice(amoCode, auditId, row.id, {
      action, reason: noticeReason.trim(), ...(action === "DELIVER" ? { delivery_channel: "PORTAL", delivery_reference: deliveryReference.trim() || "Portal audit notice" } : {}),
    }),
    onSuccess: async (row) => { setLocalError(null); setNotice(`Audit notice is now ${row.status.replaceAll("_", " ").toLowerCase()}.`); await refresh(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Audit notice transition failed."),
  });

  const personnel = personnelQuery.data || [];
  const latestNotice = useMemo(() => (noticesQuery.data?.items || []).slice().sort((a, b) => b.revision_no - a.revision_no)[0] || null, [noticesQuery.data?.items]);
  const loadError = auditQuery.error || noticesQuery.error || policiesQuery.error || meetingsQuery.error || personnelQuery.error || sessionQuery.error;

  if (auditQuery.isLoading || !draft) return <section className="qms-occurrence-stage qms-occurrence-stage--loading">Loading audit setup…</section>;
  if (loadError || !auditQuery.data) return <section className="qms-occurrence-stage qms-occurrence-stage--loading" role="alert"><AlertTriangle size={18} /> {loadError instanceof Error ? loadError.message : "Audit setup is unavailable."}</section>;

  const renderMeeting = (type: "OPENING" | "CLOSING", row: AuditMeeting | null, value: MeetingDraft, setValue: React.Dispatch<React.SetStateAction<MeetingDraft>>) => (
    <article className="qms-occurrence-stage__card">
      <header><Video size={18} /><div><strong>{type === "OPENING" ? "Opening meeting" : "Closing meeting"}</strong><small>Explicit occurrence meeting shared with authorised audit participants.</small></div></header>
      <div className="qms-occurrence-stage__fields">
        <label><span>Start</span><input type="datetime-local" disabled={!canManage} value={value.start} onChange={(event) => setValue((current) => ({ ...current, start: event.target.value }))} /></label>
        <label><span>End</span><input type="datetime-local" disabled={!canManage} value={value.end} onChange={(event) => setValue((current) => ({ ...current, end: event.target.value }))} /></label>
        <label><span>Location</span><input disabled={!canManage} value={value.location} onChange={(event) => setValue((current) => ({ ...current, location: event.target.value }))} placeholder="Room / facility" /></label>
        <label><span>Conference URL</span><input type="url" disabled={!canManage} value={value.conferenceUrl} onChange={(event) => setValue((current) => ({ ...current, conferenceUrl: event.target.value }))} placeholder="https://…" /></label>
      </div>
      <label><span>Agenda</span><textarea rows={3} disabled={!canManage} value={value.agenda} onChange={(event) => setValue((current) => ({ ...current, agenda: event.target.value }))} /></label>
      {row ? <small>Status: {row.status.replaceAll("_", " ")} · last updated {row.updated_at ? new Date(row.updated_at).toLocaleString() : "—"}</small> : <small>No meeting has been saved yet. Planned audit dates are not silently converted into meeting times.</small>}
      {canManage ? <button type="button" disabled={!value.start || meetingMutation.isPending} onClick={() => meetingMutation.mutate({ type, row, value })}><Save size={15} /> {row ? "Update meeting" : "Save meeting"}</button> : null}
    </article>
  );

  return (
    <section className="qms-occurrence-stage" aria-label="Audit setup workspace">
      <header className="qms-occurrence-stage__header">
        <div><span>SETUP · authoritative occurrence</span><h1>{auditQuery.data.audit_ref} · {auditQuery.data.title}</h1><p>Define the auditable occurrence once: scope, criteria, dates, auditee, accountable audit team, meetings and notice.</p></div>
        <div><span>{sessionQuery.data ? `Authoritative stage: ${sessionQuery.data.current_stage_label}` : "Verifying lifecycle…"}</span><button type="button" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</button></div>
      </header>
      {localError ? <div className="qms-occurrence-stage__message is-error" role="alert"><AlertTriangle size={15} /> {localError}</div> : null}
      {notice ? <div className="qms-occurrence-stage__message" role="status"><CheckCircle2 size={15} /> {notice}</div> : null}

      <div className="qms-occurrence-stage__grid">
        <main>
          <article className="qms-occurrence-stage__card">
            <header><ClipboardList size={18} /><div><strong>Audit definition</strong><small>This is the source used by preparation, fieldwork and closing.</small></div></header>
            <label><span>Audit title</span><input disabled={!canManage} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
            <label><span>Scope</span><textarea disabled={!canManage} rows={4} value={draft.scope} onChange={(event) => setDraft({ ...draft, scope: event.target.value })} /></label>
            <label><span>Criteria</span><textarea disabled={!canManage} rows={4} value={draft.criteria} onChange={(event) => setDraft({ ...draft, criteria: event.target.value })} /></label>
            <div className="qms-occurrence-stage__fields">
              <label><span>Auditee</span><input disabled={!canManage} value={draft.auditee} onChange={(event) => setDraft({ ...draft, auditee: event.target.value })} /></label>
              <label><span>Auditee email</span><input type="email" disabled={!canManage} value={draft.auditeeEmail} onChange={(event) => setDraft({ ...draft, auditeeEmail: event.target.value })} /></label>
              <label><span>Planned start</span><input type="date" disabled={!canManage} value={draft.plannedStart} onChange={(event) => setDraft({ ...draft, plannedStart: event.target.value })} /></label>
              <label><span>Planned end</span><input type="date" disabled={!canManage} value={draft.plannedEnd} onChange={(event) => setDraft({ ...draft, plannedEnd: event.target.value })} /></label>
            </div>
          </article>

          <article className="qms-occurrence-stage__card">
            <header><Users size={18} /><div><strong>Audit team</strong><small>Assignments reference existing personnel records; no shadow users are created.</small></div></header>
            <div className="qms-occurrence-stage__fields">
              {(["leadAuditorUserId", "observerAuditorUserId", "assistantAuditorUserId"] as const).map((field, index) => <label key={field}><span>{["Lead auditor", "Observer auditor", "Assistant auditor"][index]}</span><select disabled={!canManage} value={draft[field]} onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}><option value="">Unassigned</option>{personnel.map((person) => <option key={person.id} value={person.id}>{person.full_name}{person.role ? ` · ${person.role}` : ""}</option>)}</select></label>)}
              <label><span>Reminder interval (days)</span><input type="number" min={1} max={90} disabled={!canManage} value={draft.reminderIntervalDays} onChange={(event) => setDraft({ ...draft, reminderIntervalDays: event.target.value })} /></label>
            </div>
            <div className="qms-occurrence-stage__checks"><label><input type="checkbox" disabled={!canManage} checked={draft.notifyAuditors} onChange={(event) => setDraft({ ...draft, notifyAuditors: event.target.checked })} /> Notify auditors</label><label><input type="checkbox" disabled={!canManage} checked={draft.notifyAuditees} onChange={(event) => setDraft({ ...draft, notifyAuditees: event.target.checked })} /> Notify auditee</label></div>
            {canManage ? <button type="button" className="is-primary" disabled={saveMutation.isPending || draft.title.trim().length < 3 || !draft.plannedStart || !draft.plannedEnd} onClick={() => saveMutation.mutate()}><Save size={15} /> {saveMutation.isPending ? "Saving…" : "Save authoritative setup"}</button> : null}
          </article>
          {renderMeeting("OPENING", openingMeeting, openingDraft, setOpeningDraft)}
          {renderMeeting("CLOSING", closingMeeting, closingDraft, setClosingDraft)}
        </main>

        <aside>
          <article className="qms-occurrence-stage__card">
            <header><BellRing size={18} /><div><strong>Audit notice</strong><small>Versioned notice governance tied to this occurrence.</small></div></header>
            {latestNotice ? <dl><div><dt>Status</dt><dd>{latestNotice.status.replaceAll("_", " ")}</dd></div><div><dt>Revision</dt><dd>{latestNotice.revision_no}</dd></div><div><dt>Required notice</dt><dd>{latestNotice.required_notice_days} days</dd></div><div><dt>Notice date</dt><dd>{latestNotice.notice_date}</dd></div></dl> : <p>No governed notice exists yet.</p>}
            {canManage ? <><label><span>Notice decision reason</span><textarea rows={3} value={noticeReason} onChange={(event) => setNoticeReason(event.target.value)} /></label>{latestNotice?.status === "GENERATED" ? <label><span>Delivery reference</span><input value={deliveryReference} onChange={(event) => setDeliveryReference(event.target.value)} placeholder="Email/message/reference" /></label> : null}<div className="qms-occurrence-stage__actions">{!latestNotice ? <button type="button" disabled={createNoticeMutation.isPending || noticeReason.trim().length < 8} onClick={() => createNoticeMutation.mutate()}><CalendarClock size={15} /> Create notice</button> : null}{latestNotice && noticeNextAction(latestNotice) ? <button type="button" className="is-primary" disabled={transitionNoticeMutation.isPending || noticeReason.trim().length < 8} onClick={() => transitionNoticeMutation.mutate({ row: latestNotice, action: noticeNextAction(latestNotice)! })}><Send size={15} /> {noticeNextAction(latestNotice)}</button> : null}</div></> : null}
          </article>
          <article className="qms-occurrence-stage__card"><header><CalendarClock size={18} /><div><strong>Next stage</strong><small>Setup navigation does not mutate lifecycle state by itself.</small></div></header><Link className="qms-occurrence-stage__next" to={auditSessionPath(amoCode, auditKey, "prepare")}>Open Pre-Audit Room</Link></article>
        </aside>
      </div>
    </section>
  );
};

export default AuditSetupWorkspace;
