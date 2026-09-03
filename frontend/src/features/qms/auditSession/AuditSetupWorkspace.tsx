import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CalendarClock, CheckCircle2, RefreshCw, Save, Send } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { type QMSAuditOut } from "../../../services/qms";
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
import { resolveAuditOccurrence, updateAuditOccurrenceSetup } from "../../../services/qmsAuditOccurrenceResolver";
import { getAuditSession } from "../../../services/qmsAuditSession";
import AuditAssignmentGovernancePanel from "./AuditAssignmentGovernancePanel";
import { auditSessionPath } from "./auditSessionRoutes";
import "../../../styles/qms-audit-setup-workspace.css";

type Props = { amoCode: string; auditKey: string };

type SetupDraft = {
  title: string;
  scope: string;
  criteria: string;
  auditee: string;
  auditeeEmail: string;
  plannedStart: string;
  plannedEnd: string;
  notifyAuditors: boolean;
  notifyAuditees: boolean;
  reminderIntervalDays: string;
};

type SetupTileId = "definition" | "team" | "meetings" | "notice";
type MeetingModality = "" | "PHYSICAL" | "ONLINE" | "HYBRID";

type MeetingDraft = {
  modality: MeetingModality;
  customSchedule: boolean;
  start: string;
  end: string;
  location: string;
  conferenceUrl: string;
  agenda: string;
};

const emptyMeeting: MeetingDraft = {
  modality: "",
  customSchedule: false,
  start: "",
  end: "",
  location: "",
  conferenceUrl: "",
  agenda: "",
};

const MODALITY_OPTIONS: Array<{ value: Exclude<MeetingModality, "">; label: string }> = [
  { value: "PHYSICAL", label: "Physical" },
  { value: "ONLINE", label: "Online" },
  { value: "HYBRID", label: "Physical with online streaming" },
];

/** Definition planned times are locked to normal working hours. */
const WORKDAY_OPEN = "08:00";
const WORKDAY_CLOSE = "17:00";

function datePart(value: string): string {
  return (value || "").slice(0, 10);
}

function timePart(value: string, fallback: string): string {
  const match = (value || "").match(/T(\d{2}:\d{2})/);
  return match ? match[1] : fallback;
}

function clampWorkdayTime(value: string, fallback: string = WORKDAY_OPEN): string {
  const time = (value || "").slice(0, 5);
  if (!/^\d{2}:\d{2}$/.test(time)) return fallback;
  if (time < WORKDAY_OPEN) return WORKDAY_OPEN;
  if (time > WORKDAY_CLOSE) return WORKDAY_CLOSE;
  return time;
}

function composePlannedDateTime(date: string, time: string, fallbackTime: string): string {
  const day = datePart(date);
  if (!day) return "";
  return `${day}T${clampWorkdayTime(time, fallbackTime)}`;
}

function withPlannedDefaults(value: string | null | undefined, fallbackTime: string): string {
  const day = datePart(value || "");
  if (!day) return "";
  return composePlannedDateTime(day, timePart(value || "", fallbackTime), fallbackTime);
}

function dateToMeetingStart(planned: string): string {
  return withPlannedDefaults(planned, WORKDAY_OPEN);
}

function dateToMeetingEnd(planned: string): string {
  return withPlannedDefaults(planned, WORKDAY_CLOSE);
}

function formatPlannedDisplay(value: string): string {
  if (!value) return "—";
  const day = datePart(value);
  const time = timePart(value, "");
  return time ? `${day} ${time}` : day;
}

function inferModality(location: string | null | undefined, conferenceUrl: string | null | undefined): MeetingModality {
  const hasLocation = Boolean((location || "").trim() && (location || "").trim().toLowerCase() !== "online");
  const hasUrl = Boolean((conferenceUrl || "").trim());
  if (hasLocation && hasUrl) return "HYBRID";
  if (hasUrl) return "ONLINE";
  if (hasLocation) return "PHYSICAL";
  return "";
}

function meetingDraftFromRow(
  row: AuditMeeting | null,
  plannedStart: string,
  plannedEnd: string,
): MeetingDraft {
  if (!row) {
    return {
      ...emptyMeeting,
      start: dateToMeetingStart(plannedStart),
      end: dateToMeetingEnd(plannedEnd),
    };
  }
  const start = localDateTime(row.scheduled_start);
  const end = localDateTime(row.scheduled_end);
  const inheritedStart = dateToMeetingStart(plannedStart);
  const inheritedEnd = dateToMeetingEnd(plannedEnd);
  const matchesDefinition =
    Boolean(inheritedStart) &&
    start === inheritedStart &&
    (!end || !inheritedEnd || end === inheritedEnd);
  return {
    modality: inferModality(row.location, row.conference_url),
    customSchedule: !matchesDefinition,
    start,
    end,
    location: row.location || "",
    conferenceUrl: row.conference_url || "",
    agenda: row.agenda || "",
  };
}

function meetingReady(value: MeetingDraft, plannedStart: string, plannedEnd: string): boolean {
  if (!value.modality) return false;
  const start = value.customSchedule ? value.start : dateToMeetingStart(plannedStart);
  const end = value.customSchedule ? value.end : dateToMeetingEnd(plannedEnd);
  if (!start || !end) return false;
  if ((value.modality === "PHYSICAL" || value.modality === "HYBRID") && !value.location.trim()) return false;
  if ((value.modality === "ONLINE" || value.modality === "HYBRID") && !value.conferenceUrl.trim()) return false;
  return true;
}

function draftFromAudit(audit: QMSAuditOut, previous?: SetupDraft | null): SetupDraft {
  const nextStartDate = datePart(audit.planned_start || "");
  const nextEndDate = datePart(audit.planned_end || "");
  const keepStartTime =
    previous && datePart(previous.plannedStart) === nextStartDate
      ? timePart(previous.plannedStart, WORKDAY_OPEN)
      : WORKDAY_OPEN;
  const keepEndTime =
    previous && datePart(previous.plannedEnd) === nextEndDate
      ? timePart(previous.plannedEnd, WORKDAY_CLOSE)
      : WORKDAY_CLOSE;
  return {
    title: audit.title || "",
    scope: audit.scope || "",
    criteria: audit.criteria || "",
    auditee: audit.auditee || "",
    auditeeEmail: audit.auditee_email || "",
    plannedStart: withPlannedDefaults(nextStartDate ? `${nextStartDate}T${keepStartTime}` : "", WORKDAY_OPEN),
    plannedEnd: withPlannedDefaults(nextEndDate ? `${nextEndDate}T${keepEndTime}` : "", WORKDAY_CLOSE),
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

function noticeNextAction(notice: AuditNotice): "SUBMIT" | "APPROVE" | "GENERATE" | "DELIVER" | "ACKNOWLEDGE" | null {
  if (notice.status === "DRAFT") return "SUBMIT";
  if (notice.status === "UNDER_REVIEW") return "APPROVE";
  if (notice.status === "APPROVED") return "GENERATE";
  if (notice.status === "GENERATED") return "DELIVER";
  if (notice.status === "DELIVERED") return "ACKNOWLEDGE";
  return null;
}

const AuditSetupWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const location = useLocation();
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [draft, setDraft] = useState<SetupDraft | null>(null);
  const [openingDraft, setOpeningDraft] = useState<MeetingDraft>(emptyMeeting);
  const [closingDraft, setClosingDraft] = useState<MeetingDraft>(emptyMeeting);
  const [openTile, setOpenTile] = useState<SetupTileId>("definition");
  const [noticeReason, setNoticeReason] = useState("Governed audit notice created from the current occurrence setup.");
  const [deliveryReference, setDeliveryReference] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: ["qms-setup-audit-resolve", amoCode, auditKey],
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";

  useEffect(() => {
    const hash = location.hash.replace(/^#/, "");
    if (!hash) return;
    if (hash === "team" || hash === "team-wrap") setOpenTile("team");
    if (hash === "overview") setOpenTile("definition");
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(`audit-occurrence-${hash}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [location.hash, auditQuery.isSuccess]);

  const noticesQuery = useQuery({
    queryKey: ["qms-audit-notices", amoCode, auditId],
    queryFn: ({ signal }) => listAuditNotices(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const policiesQuery = useQuery({
    queryKey: ["qms-audit-notice-policies", amoCode],
    queryFn: ({ signal }) => listAuditNoticePolicies(amoCode, signal),
    enabled: Boolean(auditId),
    staleTime: 30_000,
  });
  const meetingsQuery = useQuery({
    queryKey: ["qms-audit-meetings", amoCode, auditId],
    queryFn: ({ signal }) => listAuditMeetings(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const sessionQuery = useQuery({
    queryKey: ["qms-audit-session", amoCode, auditId],
    queryFn: ({ signal }) => getAuditSession(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });

  const openingMeeting = useMemo(
    () => meetingsQuery.data?.items.find((row) => row.meeting_type === "OPENING" && row.status !== "CANCELLED") || null,
    [meetingsQuery.data?.items],
  );
  const closingMeeting = useMemo(
    () => meetingsQuery.data?.items.find((row) => row.meeting_type === "CLOSING" && row.status !== "CANCELLED") || null,
    [meetingsQuery.data?.items],
  );

  useEffect(() => {
    if (!auditQuery.data) return;
    setDraft((current) => draftFromAudit(auditQuery.data, current));
  }, [auditQuery.data]);
  useEffect(() => {
    const plannedStart = withPlannedDefaults(auditQuery.data?.planned_start || "", WORKDAY_OPEN);
    const plannedEnd = withPlannedDefaults(auditQuery.data?.planned_end || "", WORKDAY_CLOSE);
    setOpeningDraft(meetingDraftFromRow(openingMeeting, plannedStart, plannedEnd));
  }, [openingMeeting, auditQuery.data?.planned_start, auditQuery.data?.planned_end]);
  useEffect(() => {
    const plannedStart = withPlannedDefaults(auditQuery.data?.planned_start || "", WORKDAY_OPEN);
    const plannedEnd = withPlannedDefaults(auditQuery.data?.planned_end || "", WORKDAY_CLOSE);
    setClosingDraft(meetingDraftFromRow(closingMeeting, plannedStart, plannedEnd));
  }, [closingMeeting, auditQuery.data?.planned_start, auditQuery.data?.planned_end]);

  // Keep inherited schedules aligned with Definition dates while custom schedule is off.
  useEffect(() => {
    if (!draft) return;
    setOpeningDraft((current) =>
      current.customSchedule
        ? current
        : {
            ...current,
            start: dateToMeetingStart(draft.plannedStart),
            end: dateToMeetingEnd(draft.plannedEnd),
          },
    );
    setClosingDraft((current) =>
      current.customSchedule
        ? current
        : {
            ...current,
            start: dateToMeetingStart(draft.plannedStart),
            end: dateToMeetingEnd(draft.plannedEnd),
          },
    );
  }, [draft?.plannedStart, draft?.plannedEnd]);

  const selectTile = (tile: SetupTileId) => (event: React.MouseEvent<HTMLElement>) => {
    event.preventDefault();
    setOpenTile(tile);
  };

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-setup-audit-resolve", amoCode, auditKey] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-notices", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-meetings", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session-resolve", amoCode, auditKey] }),
    ]);
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!draft || !auditId) throw new Error("Audit occurrence is not ready for setup changes.");
      return updateAuditOccurrenceSetup(amoCode, auditId, {
        title: draft.title.trim(),
        scope: draft.scope.trim() || null,
        criteria: draft.criteria.trim() || null,
        auditee: draft.auditee.trim() || null,
        auditee_email: draft.auditeeEmail.trim() || null,
        planned_start: datePart(draft.plannedStart) || null,
        planned_end: datePart(draft.plannedEnd) || null,
        notify_auditors: draft.notifyAuditors,
        notify_auditees: draft.notifyAuditees,
        reminder_interval_days: Math.max(1, Number(draft.reminderIntervalDays) || 7),
      });
    },
    onSuccess: async (row) => {
      setDraft((current) => draftFromAudit(row, current));
      setLocalError(null);
      setNotice("Definition saved.");
      await refresh();
    },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Audit setup could not be saved."),
  });

  const meetingMutation = useMutation({
    mutationFn: async ({ type, row, value }: { type: "OPENING" | "CLOSING"; row: AuditMeeting | null; value: MeetingDraft }) => {
      if (!draft) throw new Error("Save the audit definition before scheduling meetings.");
      if (!value.modality) throw new Error("Select whether the meeting is physical, online, or both.");
      const start = value.customSchedule ? value.start : dateToMeetingStart(draft.plannedStart);
      const end = value.customSchedule ? value.end : dateToMeetingEnd(draft.plannedEnd);
      if (!start) throw new Error(`${type === "OPENING" ? "Opening" : "Closing"} meeting start is required.`);
      if (!end) throw new Error(`${type === "OPENING" ? "Opening" : "Closing"} meeting end is required.`);
      if ((value.modality === "PHYSICAL" || value.modality === "HYBRID") && !value.location.trim()) {
        throw new Error("Physical location is required for this meeting modality.");
      }
      if ((value.modality === "ONLINE" || value.modality === "HYBRID") && !value.conferenceUrl.trim()) {
        throw new Error("Conference URL is required for online or streamed meetings.");
      }
      const payload = {
        meeting_type: type,
        scheduled_start: new Date(start).toISOString(),
        scheduled_end: new Date(end).toISOString(),
        location: value.modality === "ONLINE" ? null : value.location.trim() || null,
        conference_url: value.modality === "PHYSICAL" ? null : value.conferenceUrl.trim() || null,
        agenda: value.agenda.trim() || null,
        status: (row?.status || "PLANNED") as const,
      };
      return row ? updateAuditMeeting(amoCode, auditId, row.id, payload) : createAuditMeeting(amoCode, auditId, payload);
    },
    onSuccess: async (row) => {
      setLocalError(null);
      setNotice(`${row.meeting_type === "OPENING" ? "Opening" : "Closing"} meeting saved.`);
      await refresh();
    },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Audit meeting could not be saved."),
  });

  const createNoticeMutation = useMutation({
    mutationFn: async () => {
      if (!auditQuery.data || !draft) throw new Error("Save the audit occurrence before creating its notice.");
      const policy =
        policiesQuery.data?.items.find((item) => !item.audit_kind || item.audit_kind === auditQuery.data?.kind) ||
        policiesQuery.data?.items[0];
      return createAuditNotice(amoCode, auditId, {
        policy_id: policy?.id,
        notice_date: new Date().toISOString().slice(0, 10),
        subject: `${auditQuery.data.audit_ref} · ${draft.title}`,
        body: `Audit scope: ${draft.scope || "Not specified"}\nCriteria: ${draft.criteria || "Not specified"}\nPlanned: ${draft.plannedStart || "TBC"} to ${draft.plannedEnd || "TBC"}`,
        reason: noticeReason.trim(),
      });
    },
    onSuccess: async () => {
      setLocalError(null);
      setNotice("Notice draft created.");
      await refresh();
    },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Audit notice could not be created."),
  });

  const transitionNoticeMutation = useMutation({
    mutationFn: ({ row, action }: { row: AuditNotice; action: NonNullable<ReturnType<typeof noticeNextAction>> }) =>
      transitionAuditNotice(amoCode, auditId, row.id, {
        action,
        reason: noticeReason.trim(),
        ...(action === "DELIVER"
          ? { delivery_channel: "PORTAL", delivery_reference: deliveryReference.trim() || "Portal audit notice" }
          : {}),
      }),
    onSuccess: async (row) => {
      setLocalError(null);
      setNotice(`Notice ${row.status.replaceAll("_", " ").toLowerCase()}.`);
      await refresh();
    },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Audit notice transition failed."),
  });

  const latestNotice = useMemo(
    () => (noticesQuery.data?.items || []).slice().sort((a, b) => b.revision_no - a.revision_no)[0] || null,
    [noticesQuery.data?.items],
  );
  const loadError = auditQuery.error || noticesQuery.error || policiesQuery.error || meetingsQuery.error || sessionQuery.error;
  const teamAssigned = Boolean(
    auditQuery.data?.lead_auditor_user_id ||
      auditQuery.data?.observer_auditor_user_id ||
      auditQuery.data?.assistant_auditor_user_id,
  );
  const nextNotice = latestNotice ? noticeNextAction(latestNotice) : null;

  if (auditQuery.isLoading || !draft) {
    return <section className="qms-occurrence-stage qms-occurrence-stage--loading">Loading audit setup…</section>;
  }
  if (loadError || !auditQuery.data) {
    return (
      <section className="qms-occurrence-stage qms-occurrence-stage--loading" role="alert">
        <AlertTriangle size={18} /> {loadError instanceof Error ? loadError.message : "Audit setup is unavailable."}
      </section>
    );
  }

  const renderMeeting = (
    type: "OPENING" | "CLOSING",
    row: AuditMeeting | null,
    value: MeetingDraft,
    setValue: React.Dispatch<React.SetStateAction<MeetingDraft>>,
  ) => {
    const needsLocation = value.modality === "PHYSICAL" || value.modality === "HYBRID";
    const needsUrl = value.modality === "ONLINE" || value.modality === "HYBRID";
    return (
      <div className="qms-audit-setup-stage__meeting">
        <strong>{type === "OPENING" ? "Opening" : "Closing"}</strong>

        <fieldset className="qms-audit-setup-stage__modality" disabled={!canManage}>
          <legend>Format</legend>
          <div className="qms-audit-setup-stage__modality-options">
            {MODALITY_OPTIONS.map((option) => (
              <label key={option.value}>
                <input
                  type="radio"
                  name={`${type.toLowerCase()}-modality`}
                  checked={value.modality === option.value}
                  onChange={() =>
                    setValue((current) => ({
                      ...current,
                      modality: option.value,
                      location: option.value === "ONLINE" ? "" : current.location,
                      conferenceUrl: option.value === "PHYSICAL" ? "" : current.conferenceUrl,
                    }))
                  }
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>

        {!value.modality ? <p className="qms-audit-setup-stage__empty">Select format before scheduling.</p> : null}

        {value.modality ? (
          <>
            <label className="qms-audit-setup-stage__check-row">
              <input
                type="checkbox"
                disabled={!canManage}
                checked={value.customSchedule}
                onChange={(event) => {
                  const customSchedule = event.target.checked;
                  setValue((current) => ({
                    ...current,
                    customSchedule,
                    start: customSchedule ? current.start || dateToMeetingStart(draft.plannedStart) : dateToMeetingStart(draft.plannedStart),
                    end: customSchedule ? current.end || dateToMeetingEnd(draft.plannedEnd) : dateToMeetingEnd(draft.plannedEnd),
                  }));
                }}
              />
              Different schedule from Definition dates
            </label>

            {value.customSchedule ? (
              <div className="qms-audit-setup-stage__fields">
                <label>
                  <span>Start</span>
                  <input
                    type="datetime-local"
                    disabled={!canManage}
                    value={value.start}
                    onChange={(event) => setValue((current) => ({ ...current, start: event.target.value }))}
                  />
                </label>
                <label>
                  <span>End</span>
                  <input
                    type="datetime-local"
                    disabled={!canManage}
                    value={value.end}
                    onChange={(event) => setValue((current) => ({ ...current, end: event.target.value }))}
                  />
                </label>
              </div>
            ) : (
              <p className="qms-audit-setup-stage__schedule-inherit">
                Uses Definition schedule: <strong>{formatPlannedDisplay(draft.plannedStart)}</strong> →{" "}
                <strong>{formatPlannedDisplay(draft.plannedEnd)}</strong>
              </p>
            )}

            <div className="qms-audit-setup-stage__fields">
              {needsLocation ? (
                <label>
                  <span>Location</span>
                  <input
                    disabled={!canManage}
                    value={value.location}
                    onChange={(event) => setValue((current) => ({ ...current, location: event.target.value }))}
                    placeholder="Room / facility"
                  />
                </label>
              ) : null}
              {needsUrl ? (
                <label>
                  <span>Conference URL</span>
                  <input
                    type="url"
                    disabled={!canManage}
                    value={value.conferenceUrl}
                    onChange={(event) => setValue((current) => ({ ...current, conferenceUrl: event.target.value }))}
                    placeholder="https://…"
                  />
                </label>
              ) : null}
            </div>

            <label>
              <span>Agenda</span>
              <textarea
                rows={2}
                disabled={!canManage}
                value={value.agenda}
                onChange={(event) => setValue((current) => ({ ...current, agenda: event.target.value }))}
              />
            </label>
            <small>{row ? row.status.replaceAll("_", " ") : "Not saved"}</small>
            {canManage ? (
              <div className="qms-audit-setup-stage__actions">
                <button
                  type="button"
                  disabled={!meetingReady(value, draft.plannedStart, draft.plannedEnd) || meetingMutation.isPending}
                  onClick={() => meetingMutation.mutate({ type, row, value })}
                >
                  <Save size={15} /> {row ? "Update" : "Save"}
                </button>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    );
  };

  const meetingCount = [openingMeeting, closingMeeting].filter(Boolean).length;
  const definitionSummary = [
    draft.title,
    draft.plannedStart && draft.plannedEnd
      ? `${formatPlannedDisplay(draft.plannedStart)} → ${formatPlannedDisplay(draft.plannedEnd)}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <section className="qms-occurrence-stage qms-audit-setup-stage" aria-label="Audit setup workspace" id="audit-occurrence-overview">
      <div className="qms-audit-setup-stage__toolbar">
        <div className="qms-audit-setup-stage__intro">
          <h2 className="qms-audit-setup-stage__title">Setup</h2>
          <p className="qms-audit-setup-stage__helper">Define the audit, assign the team, schedule meetings, and issue notice.</p>
          <div className="qms-audit-setup-stage__status" role="status" aria-label="Setup status">
            <span className={`qms-audit-setup-stage__chip${teamAssigned ? "" : " is-warning"}`}>
              Team {teamAssigned ? "assigned" : "unassigned"}
            </span>
            <span className={`qms-audit-setup-stage__chip${latestNotice ? "" : " is-warning"}`}>
              Notice {latestNotice ? latestNotice.status.replaceAll("_", " ") : "none"}
            </span>
            <span className={`qms-audit-setup-stage__chip${meetingCount < 2 ? " is-warning" : ""}`}>
              Meetings {meetingCount}/2
            </span>
          </div>
        </div>
        <div className="qms-audit-setup-stage__toolbar-actions">
          <Link className="qms-occurrence-stage__next" to={auditSessionPath(amoCode, auditKey, "prepare")}>
            Continue to Prepare
            <ArrowRight size={16} aria-hidden />
          </Link>
          <button type="button" onClick={() => void refresh()} aria-label="Refresh setup">
            <RefreshCw size={15} />
          </button>
          <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits`}>Exit</Link>
        </div>
      </div>

      {localError ? (
        <div className="qms-occurrence-stage__message is-error" role="alert">
          <AlertTriangle size={15} /> {localError}
        </div>
      ) : null}
      {notice ? (
        <div className="qms-occurrence-stage__message" role="status">
          <CheckCircle2 size={15} /> {notice}
        </div>
      ) : null}

      <div className="qms-audit-setup-stage__tiles">
        <details className="qms-audit-setup-tile" open={openTile === "definition"}>
          <summary onClick={selectTile("definition")}>
            <span className="qms-audit-setup-tile__title">Definition</span>
            <span className="qms-audit-setup-tile__hint">{definitionSummary || "Title, scope, dates"}</span>
          </summary>
          <div className="qms-audit-setup-tile__body">
            <label>
              <span>Title</span>
              <input disabled={!canManage} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
            </label>
            <div className="qms-audit-setup-stage__fields">
              <label>
                <span>Scope</span>
                <textarea
                  disabled={!canManage}
                  rows={2}
                  value={draft.scope}
                  onChange={(event) => setDraft({ ...draft, scope: event.target.value })}
                />
              </label>
              <label>
                <span>Criteria</span>
                <textarea
                  disabled={!canManage}
                  rows={2}
                  value={draft.criteria}
                  onChange={(event) => setDraft({ ...draft, criteria: event.target.value })}
                />
              </label>
            </div>
            <div className="qms-audit-setup-stage__fields">
              <label>
                <span>Auditee</span>
                <input
                  disabled={!canManage}
                  value={draft.auditee}
                  onChange={(event) => setDraft({ ...draft, auditee: event.target.value })}
                />
              </label>
              <label>
                <span>Auditee email</span>
                <input
                  type="email"
                  disabled={!canManage}
                  value={draft.auditeeEmail}
                  onChange={(event) => setDraft({ ...draft, auditeeEmail: event.target.value })}
                />
              </label>
              <label>
                <span>Planned start</span>
                <div className="qms-audit-setup-stage__datetime">
                  <input
                    type="date"
                    disabled={!canManage}
                    value={datePart(draft.plannedStart)}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        plannedStart: composePlannedDateTime(
                          event.target.value,
                          timePart(draft.plannedStart, WORKDAY_OPEN),
                          WORKDAY_OPEN,
                        ),
                      })
                    }
                  />
                  <input
                    type="time"
                    min={WORKDAY_OPEN}
                    max={WORKDAY_CLOSE}
                    step={300}
                    disabled={!canManage || !datePart(draft.plannedStart)}
                    value={timePart(draft.plannedStart, WORKDAY_OPEN)}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        plannedStart: composePlannedDateTime(
                          datePart(draft.plannedStart),
                          event.target.value,
                          WORKDAY_OPEN,
                        ),
                      })
                    }
                    onBlur={(event) =>
                      setDraft({
                        ...draft,
                        plannedStart: composePlannedDateTime(
                          datePart(draft.plannedStart),
                          event.target.value,
                          WORKDAY_OPEN,
                        ),
                      })
                    }
                  />
                </div>
              </label>
              <label>
                <span>Planned end</span>
                <div className="qms-audit-setup-stage__datetime">
                  <input
                    type="date"
                    disabled={!canManage}
                    value={datePart(draft.plannedEnd)}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        plannedEnd: composePlannedDateTime(
                          event.target.value,
                          timePart(draft.plannedEnd, WORKDAY_CLOSE),
                          WORKDAY_CLOSE,
                        ),
                      })
                    }
                  />
                  <input
                    type="time"
                    min={WORKDAY_OPEN}
                    max={WORKDAY_CLOSE}
                    step={300}
                    disabled={!canManage || !datePart(draft.plannedEnd)}
                    value={timePart(draft.plannedEnd, WORKDAY_CLOSE)}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        plannedEnd: composePlannedDateTime(
                          datePart(draft.plannedEnd),
                          event.target.value,
                          WORKDAY_CLOSE,
                        ),
                      })
                    }
                    onBlur={(event) =>
                      setDraft({
                        ...draft,
                        plannedEnd: composePlannedDateTime(
                          datePart(draft.plannedEnd),
                          event.target.value,
                          WORKDAY_CLOSE,
                        ),
                      })
                    }
                  />
                </div>
              </label>
              <label>
                <span>Reminder (days)</span>
                <input
                  type="number"
                  min={1}
                  max={60}
                  disabled={!canManage}
                  value={draft.reminderIntervalDays}
                  onChange={(event) => setDraft({ ...draft, reminderIntervalDays: event.target.value })}
                />
              </label>
            </div>
            <div className="qms-audit-setup-stage__checks">
              <label>
                <input
                  type="checkbox"
                  disabled={!canManage}
                  checked={draft.notifyAuditors}
                  onChange={(event) => setDraft({ ...draft, notifyAuditors: event.target.checked })}
                />
                Notify auditors
              </label>
              <label>
                <input
                  type="checkbox"
                  disabled={!canManage}
                  checked={draft.notifyAuditees}
                  onChange={(event) => setDraft({ ...draft, notifyAuditees: event.target.checked })}
                />
                Notify auditee
              </label>
            </div>
            {canManage ? (
              <div className="qms-audit-setup-stage__actions">
                <button
                  type="button"
                  className="is-primary"
                  disabled={
                    saveMutation.isPending || draft.title.trim().length < 3 || !draft.plannedStart || !draft.plannedEnd
                  }
                  onClick={() => saveMutation.mutate()}
                >
                  <Save size={15} /> {saveMutation.isPending ? "Saving…" : "Save definition"}
                </button>
              </div>
            ) : null}
          </div>
        </details>

        <details className="qms-audit-setup-tile" id="audit-occurrence-team-wrap" open={openTile === "team"}>
          <summary onClick={selectTile("team")}>
            <span className="qms-audit-setup-tile__title">Team</span>
            <span className={`qms-audit-setup-tile__hint${teamAssigned ? "" : " is-warning"}`}>
              {teamAssigned ? "Assigned" : "Needs assignment"}
            </span>
          </summary>
          <div className="qms-audit-setup-tile__body">
            <AuditAssignmentGovernancePanel amoCode={amoCode} auditKey={auditKey} />
          </div>
        </details>

        <details className="qms-audit-setup-tile" open={openTile === "meetings"}>
          <summary onClick={selectTile("meetings")}>
            <span className="qms-audit-setup-tile__title">Meetings</span>
            <span className={`qms-audit-setup-tile__hint${meetingCount < 2 ? " is-warning" : ""}`}>
              {meetingCount}/2 scheduled
            </span>
          </summary>
          <div className="qms-audit-setup-tile__body">
            <div className="qms-audit-setup-stage__meetings">
              {renderMeeting("OPENING", openingMeeting, openingDraft, setOpeningDraft)}
              {renderMeeting("CLOSING", closingMeeting, closingDraft, setClosingDraft)}
            </div>
          </div>
        </details>

        <details className="qms-audit-setup-tile" open={openTile === "notice"}>
          <summary onClick={selectTile("notice")}>
            <span className="qms-audit-setup-tile__title">Notice</span>
            <span className={`qms-audit-setup-tile__hint${latestNotice ? "" : " is-warning"}`}>
              {latestNotice ? latestNotice.status.replaceAll("_", " ") : "Not created"}
            </span>
          </summary>
          <div className="qms-audit-setup-tile__body">
            {latestNotice ? (
              <dl className="qms-audit-setup-stage__notice-meta">
                <div>
                  <dt>Status</dt>
                  <dd>{latestNotice.status.replaceAll("_", " ")}</dd>
                </div>
                <div>
                  <dt>Revision</dt>
                  <dd>{latestNotice.revision_no}</dd>
                </div>
                <div>
                  <dt>Required days</dt>
                  <dd>{latestNotice.required_notice_days}</dd>
                </div>
                <div>
                  <dt>Notice date</dt>
                  <dd>{latestNotice.notice_date}</dd>
                </div>
              </dl>
            ) : (
              <p className="qms-audit-setup-stage__empty">No notice yet.</p>
            )}
            {canManage ? (
              <>
                <label>
                  <span>Decision reason</span>
                  <textarea rows={2} value={noticeReason} onChange={(event) => setNoticeReason(event.target.value)} />
                </label>
                {latestNotice?.status === "GENERATED" ? (
                  <label>
                    <span>Delivery reference</span>
                    <input
                      value={deliveryReference}
                      onChange={(event) => setDeliveryReference(event.target.value)}
                      placeholder="Email / message ref"
                    />
                  </label>
                ) : null}
                <div className="qms-audit-setup-stage__actions">
                  {!latestNotice ? (
                    <button
                      type="button"
                      disabled={createNoticeMutation.isPending || noticeReason.trim().length < 8}
                      onClick={() => createNoticeMutation.mutate()}
                    >
                      <CalendarClock size={15} /> Create notice
                    </button>
                  ) : null}
                  {latestNotice && nextNotice ? (
                    <button
                      type="button"
                      className="is-primary"
                      disabled={transitionNoticeMutation.isPending || noticeReason.trim().length < 8}
                      onClick={() => transitionNoticeMutation.mutate({ row: latestNotice, action: nextNotice })}
                    >
                      <Send size={15} /> {nextNotice}
                    </button>
                  ) : null}
                </div>
              </>
            ) : null}
          </div>
        </details>
      </div>
    </section>
  );
};

export default AuditSetupWorkspace;
