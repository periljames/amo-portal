import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CalendarClock, CheckCircle2, Download, Eye, FileUp, RefreshCw, Save, Send, X } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { type QMSAuditOut } from "../../../services/qms";
import {
  createAuditNotice,
  downloadAuditNoticeDocument,
  listAuditNotices,
  listAuditNoticePolicies,
  previewAuditNoticePdf,
  submitAuditNotice,
  uploadAuditNoticeAttachment,
  type AuditNotice,
} from "../../../services/qmsAuditGovernance";
import { downloadBlob } from "../../../services/typedApi";
import {
  createAuditMeeting,
  listAuditMeetings,
  updateAuditMeeting,
  type AuditMeeting,
} from "../../../services/qmsAuditOccurrenceCompletion";
import {
  auditOccurrenceQueryKey,
  resolveAuditOccurrence,
  updateAuditOccurrenceSetup,
} from "../../../services/qmsAuditOccurrenceResolver";
import AuditAssignmentGovernancePanel from "./AuditAssignmentGovernancePanel";
import { AuditStageLoadError } from "./AuditStageLoadError";
import { auditSetupReadiness } from "./auditSetupModel";
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
};

const emptyMeeting: MeetingDraft = {
  modality: "",
  customSchedule: false,
  start: "",
  end: "",
  location: "",
  conferenceUrl: "",
};

const MODALITY_OPTIONS: Array<{ value: Exclude<MeetingModality, "">; label: string }> = [
  { value: "PHYSICAL", label: "Physical" },
  { value: "ONLINE", label: "Online" },
  { value: "HYBRID", label: "Physical with online streaming" },
];

const OPENING_MEETING_START = "08:00";
const OPENING_MEETING_END = "09:00";
const CLOSING_MEETING_START = "16:00";
const CLOSING_MEETING_END = "17:00";

function datePart(value: string): string {
  return (value || "").slice(0, 10);
}

function formatPlannedDisplay(value: string): string {
  return datePart(value) || "—";
}

function inheritedMeetingWindow(
  type: "OPENING" | "CLOSING",
  plannedStart: string,
  plannedEnd: string,
): { start: string; end: string } {
  const day = datePart(type === "OPENING" ? plannedStart : plannedEnd);
  if (!day) return { start: "", end: "" };
  return type === "OPENING"
    ? { start: `${day}T${OPENING_MEETING_START}`, end: `${day}T${OPENING_MEETING_END}` }
    : { start: `${day}T${CLOSING_MEETING_START}`, end: `${day}T${CLOSING_MEETING_END}` };
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
  type: "OPENING" | "CLOSING",
  plannedStart: string,
  plannedEnd: string,
): MeetingDraft {
  const inherited = inheritedMeetingWindow(type, plannedStart, plannedEnd);
  if (!row) {
    return {
      ...emptyMeeting,
      ...inherited,
    };
  }
  const start = localDateTime(row.scheduled_start);
  const end = localDateTime(row.scheduled_end);
  const matchesDefinition =
    Boolean(inherited.start) && start === inherited.start && (!end || !inherited.end || end === inherited.end);
  return {
    modality: inferModality(row.location, row.conference_url),
    customSchedule: !matchesDefinition,
    start,
    end,
    location: row.location || "",
    conferenceUrl: row.conference_url || "",
  };
}

function meetingReady(
  type: "OPENING" | "CLOSING",
  value: MeetingDraft,
  plannedStart: string,
  plannedEnd: string,
): boolean {
  if (!value.modality) return false;
  const inherited = inheritedMeetingWindow(type, plannedStart, plannedEnd);
  const start = value.customSchedule ? value.start : inherited.start;
  const end = value.customSchedule ? value.end : inherited.end;
  if (!start || !end) return false;
  if (end < start) return false;
  if ((value.modality === "PHYSICAL" || value.modality === "HYBRID") && !value.location.trim()) return false;
  if ((value.modality === "ONLINE" || value.modality === "HYBRID") && !value.conferenceUrl.trim()) return false;
  return true;
}

function draftFromAudit(audit: QMSAuditOut): SetupDraft {
  return {
    title: audit.title || "",
    scope: audit.scope || "",
    criteria: audit.criteria || "",
    auditee: audit.auditee || "",
    auditeeEmail: audit.auditee_email || "",
    plannedStart: datePart(audit.planned_start || ""),
    plannedEnd: datePart(audit.planned_end || ""),
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

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim() ? error.message : fallback;
}

const AuditSetupWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const location = useLocation();
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const canManageNotice = canManage || hasQmsRolePermission("qms.audit.notice.manage");
  const [draft, setDraft] = useState<SetupDraft | null>(null);
  const [openingDraft, setOpeningDraft] = useState<MeetingDraft>(emptyMeeting);
  const [closingDraft, setClosingDraft] = useState<MeetingDraft>(emptyMeeting);
  const [openTile, setOpenTile] = useState<SetupTileId>("definition");
  const [noticeReason, setNoticeReason] = useState("Audit notice preview verified and submitted from the current occurrence setup.");
  const [noticePreview, setNoticePreview] = useState<{ url: string; filename: string; noticeId: string } | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const url = noticePreview?.url;
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [noticePreview?.url]);

  useEffect(() => {
    if (!noticePreview) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setNoticePreview(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [noticePreview]);

  const auditQuery = useQuery({
    queryKey: auditOccurrenceQueryKey(amoCode, auditKey),
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";

  useEffect(() => {
    const hash = location.hash.replace(/^#/, "");
    if (!hash) return;
    const frame = window.requestAnimationFrame(() => {
      if (hash === "team" || hash === "team-wrap") setOpenTile("team");
      if (hash === "overview") setOpenTile("definition");
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
  const openingMeeting = useMemo(
    () => meetingsQuery.data?.items.find((row) => row.meeting_type === "OPENING" && row.status !== "CANCELLED") || null,
    [meetingsQuery.data?.items],
  );
  const closingMeeting = useMemo(
    () => meetingsQuery.data?.items.find((row) => row.meeting_type === "CLOSING" && row.status !== "CANCELLED") || null,
    [meetingsQuery.data?.items],
  );

  useEffect(() => {
    const row = auditQuery.data;
    if (!row) return;
    const frame = window.requestAnimationFrame(() => {
      setDraft(draftFromAudit(row));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [auditQuery.data]);
  useEffect(() => {
    const plannedStart = datePart(auditQuery.data?.planned_start || "");
    const plannedEnd = datePart(auditQuery.data?.planned_end || "");
    const frame = window.requestAnimationFrame(() => {
      setOpeningDraft(meetingDraftFromRow(openingMeeting, "OPENING", plannedStart, plannedEnd));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [openingMeeting, auditQuery.data?.planned_start, auditQuery.data?.planned_end]);
  useEffect(() => {
    const plannedStart = datePart(auditQuery.data?.planned_start || "");
    const plannedEnd = datePart(auditQuery.data?.planned_end || "");
    const frame = window.requestAnimationFrame(() => {
      setClosingDraft(meetingDraftFromRow(closingMeeting, "CLOSING", plannedStart, plannedEnd));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [closingMeeting, auditQuery.data?.planned_start, auditQuery.data?.planned_end]);

  // Keep inherited schedules aligned with Definition dates while custom schedule is off.
  const inheritedPlannedStart = draft?.plannedStart;
  const inheritedPlannedEnd = draft?.plannedEnd;
  useEffect(() => {
    if (inheritedPlannedStart === undefined || inheritedPlannedEnd === undefined) return;
    const frame = window.requestAnimationFrame(() => {
      const openingWindow = inheritedMeetingWindow("OPENING", inheritedPlannedStart, inheritedPlannedEnd);
      const closingWindow = inheritedMeetingWindow("CLOSING", inheritedPlannedStart, inheritedPlannedEnd);
      setOpeningDraft((current) =>
        current.customSchedule
          ? current
          : {
              ...current,
              ...openingWindow,
            },
      );
      setClosingDraft((current) =>
        current.customSchedule
          ? current
          : {
              ...current,
              ...closingWindow,
            },
      );
    });
    return () => window.cancelAnimationFrame(frame);
  }, [inheritedPlannedStart, inheritedPlannedEnd]);

  const selectTile = (tile: SetupTileId) => (event: React.MouseEvent<HTMLElement>) => {
    event.preventDefault();
    setOpenTile(tile);
  };

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: auditOccurrenceQueryKey(amoCode, auditKey) }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-notices", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-meetings", amoCode, auditId] }),
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
      setDraft(draftFromAudit(row));
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
      const inherited = inheritedMeetingWindow(type, draft.plannedStart, draft.plannedEnd);
      const start = value.customSchedule ? value.start : inherited.start;
      const end = value.customSchedule ? value.end : inherited.end;
      if (!start) throw new Error(`${type === "OPENING" ? "Opening" : "Closing"} meeting start is required.`);
      if (!end) throw new Error(`${type === "OPENING" ? "Opening" : "Closing"} meeting end is required.`);
      if (end < start) throw new Error("Meeting end cannot be before its start.");
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
        status: row?.status ?? "PLANNED",
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

  const previewNoticeMutation = useMutation({
    mutationFn: async (row: AuditNotice) => ({ row, ...(await previewAuditNoticePdf(amoCode, auditId, row.id)) }),
    onSuccess: ({ row, blob, filename }) => {
      setLocalError(null);
      setNoticePreview({
        url: URL.createObjectURL(blob),
        filename: filename || row.artifact?.filename || `audit-notice-r${row.revision_no}.pdf`,
        noticeId: row.id,
      });
    },
    onError: (cause) => setLocalError(errorMessage(cause, "The audit notice preview could not be generated.")),
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
        reason: noticeReason.trim(),
      });
    },
    onSuccess: async (row) => {
      setLocalError(null);
      setNotice("Notice draft prepared from the saved audit data.");
      await refresh();
      previewNoticeMutation.mutate(row);
    },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Audit notice could not be created."),
  });

  const uploadNoticeMutation = useMutation({
    mutationFn: ({ row, file }: { row: AuditNotice; file: File }) => {
      if (file.type && file.type !== "application/pdf") throw new Error("Select a PDF audit notice.");
      if (file.size > 15 * 1024 * 1024) throw new Error("The audit notice PDF must not exceed 15 MiB.");
      return uploadAuditNoticeAttachment(amoCode, auditId, row.id, file);
    },
    onSuccess: async (row) => {
      setLocalError(null);
      setNotice("Signed notice PDF attached. Preview it before submission.");
      await refresh();
      previewNoticeMutation.mutate(row);
    },
    onError: (cause) => setLocalError(errorMessage(cause, "The audit notice PDF could not be attached.")),
  });

  const submitNoticeMutation = useMutation({
    mutationFn: (row: AuditNotice) => submitAuditNotice(amoCode, auditId, row.id, noticeReason.trim()),
    onSuccess: async (result) => {
      setLocalError(null);
      setNotice(
        result.delivery_complete
          ? `Notice submitted with its PDF attached to ${result.dispatch.sent} email${result.dispatch.sent === 1 ? "" : "s"}.`
          : `The notice PDF is ready, but ${result.dispatch.failed} of ${result.dispatch.attempted} email deliveries failed. Correct the email configuration and retry.`,
      );
      await refresh();
      previewNoticeMutation.mutate(result.notice);
    },
    onError: (cause) => setLocalError(errorMessage(cause, "The audit notice could not be submitted.")),
  });

  const downloadNoticeMutation = useMutation({
    mutationFn: async (row: AuditNotice) => ({ row, ...(await downloadAuditNoticeDocument(amoCode, auditId, row.id)) }),
    onSuccess: ({ row, blob, filename }) => downloadBlob(blob, filename || row.artifact?.filename || "audit-notice.pdf"),
    onError: (cause) => setLocalError(errorMessage(cause, "The audit notice PDF could not be downloaded.")),
  });

  const latestNotice = useMemo(
    () => (noticesQuery.data?.items || []).slice().sort((a, b) => b.revision_no - a.revision_no)[0] || null,
    [noticesQuery.data?.items],
  );
  const previewedNotice = noticePreview
    ? (noticesQuery.data?.items || []).find((item) => item.id === noticePreview.noticeId) || latestNotice
    : null;

  if (auditQuery.isLoading && !auditQuery.data) {
    return <section className="qms-occurrence-stage qms-occurrence-stage--loading">Loading audit setup…</section>;
  }
  if (auditQuery.isError || !auditQuery.data) {
    return (
      <AuditStageLoadError
        className="qms-occurrence-stage qms-occurrence-stage--loading qms-audit-stage-load-error"
        title="Audit Setup is unavailable"
        detail={errorMessage(auditQuery.error, "The audit occurrence could not be resolved.")}
        onRetry={() => void auditQuery.refetch()}
        exitHref={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits`}
      />
    );
  }
  if (!draft) {
    return <section className="qms-occurrence-stage qms-occurrence-stage--loading">Preparing audit setup…</section>;
  }

  const persistedDraft = draftFromAudit(auditQuery.data);
  const definitionDirty = JSON.stringify(draft) !== JSON.stringify(persistedDraft);
  const readiness = auditSetupReadiness({
    ...draft,
    leadAuditorUserId: auditQuery.data.lead_auditor_user_id,
  });
  const setupReady = readiness.ready && !definitionDirty;
  const supportingErrorCount = [meetingsQuery.error, noticesQuery.error, policiesQuery.error].filter(Boolean).length;

  const renderMeeting = (
    type: "OPENING" | "CLOSING",
    row: AuditMeeting | null,
    value: MeetingDraft,
    setValue: React.Dispatch<React.SetStateAction<MeetingDraft>>,
  ) => {
    const needsLocation = value.modality === "PHYSICAL" || value.modality === "HYBRID";
    const needsUrl = value.modality === "ONLINE" || value.modality === "HYBRID";
    const inherited = inheritedMeetingWindow(type, draft.plannedStart, draft.plannedEnd);
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
                    start: customSchedule ? current.start || inherited.start : inherited.start,
                    end: customSchedule ? current.end || inherited.end : inherited.end,
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
                Suggested from audit dates: <strong>{inherited.start.replace("T", " ") || "Set audit dates first"}</strong>
                {inherited.end ? <> → <strong>{inherited.end.replace("T", " ")}</strong></> : null}
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

            <small>{row ? row.status.replaceAll("_", " ") : "Not saved"}</small>
            {canManage ? (
              <div className="qms-audit-setup-stage__actions">
                <button
                  type="button"
                  disabled={!meetingReady(type, value, draft.plannedStart, draft.plannedEnd) || meetingMutation.isPending}
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
          <p className="qms-audit-setup-stage__helper">
            Complete the required definition and lead-auditor steps first. Meetings and notice can then be prepared here.
          </p>
          <div className="qms-audit-setup-stage__status" role="status" aria-label="Setup status">
            <span className={`qms-audit-setup-stage__chip${readiness.definitionReady ? "" : " is-warning"}`}>
              Definition {readiness.definitionReady ? "complete" : "incomplete"}
            </span>
            <span className={`qms-audit-setup-stage__chip${readiness.leadAssigned ? "" : " is-warning"}`}>
              Lead auditor {readiness.leadAssigned ? "assigned" : "missing"}
            </span>
            <span className="qms-audit-setup-stage__chip">
              Meetings {meetingsQuery.isPending ? "loading…" : `${meetingCount}/2`}
            </span>
            <span className="qms-audit-setup-stage__chip">
              Notice {noticesQuery.isPending ? "loading…" : latestNotice ? latestNotice.status.replaceAll("_", " ") : "not started"}
            </span>
          </div>
        </div>
        <div className="qms-audit-setup-stage__toolbar-actions">
          {setupReady ? (
            <Link className="qms-occurrence-stage__next" to={auditSessionPath(amoCode, auditKey, "prepare")}>
              Continue to Prepare
              <ArrowRight size={16} aria-hidden />
            </Link>
          ) : (
            <button
              type="button"
              className="qms-occurrence-stage__next"
              disabled
              title={definitionDirty ? "Save the audit definition before continuing." : readiness.issues.join(" ")}
            >
              Continue to Prepare
              <ArrowRight size={16} aria-hidden />
            </button>
          )}
          <button type="button" onClick={() => void refresh()} aria-label="Refresh setup">
            <RefreshCw size={15} />
          </button>
          <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits`}>Exit</Link>
        </div>
      </div>

      <div className={`qms-audit-setup-stage__readiness${setupReady ? " is-ready" : ""}`} role="status">
        {setupReady ? <CheckCircle2 size={17} aria-hidden /> : <AlertTriangle size={17} aria-hidden />}
        <div>
          <strong>{setupReady ? "Required setup is complete" : "Complete setup before Prepare"}</strong>
          <p>
            {setupReady
              ? "Scope, criteria, audit dates, auditee and lead auditor are saved. Meetings and notice remain visible as governance tasks."
              : definitionDirty
                ? "Save the audit definition before continuing."
                : readiness.issues.join(" ")}
          </p>
        </div>
      </div>

      {supportingErrorCount ? (
        <div className="qms-audit-setup-stage__supporting-warning" role="status">
          <AlertTriangle size={15} aria-hidden />
          Setup remains available, but {supportingErrorCount} supporting section{supportingErrorCount === 1 ? "" : "s"} could not be loaded. Open the affected step to retry.
        </div>
      ) : null}

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
            <span className="qms-audit-setup-tile__step" aria-hidden>1</span>
            <span className="qms-audit-setup-tile__title">Audit definition</span>
            <span className="qms-audit-setup-tile__hint">{definitionSummary || "Title, scope, dates"}</span>
            <span className={`qms-audit-setup-tile__state${readiness.definitionReady ? " is-complete" : " is-required"}`}>
              {readiness.definitionReady ? "Complete" : "Required"}
            </span>
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
                <input
                  type="date"
                  disabled={!canManage}
                  value={draft.plannedStart}
                  onChange={(event) => setDraft({ ...draft, plannedStart: event.target.value })}
                />
              </label>
              <label>
                <span>Planned end</span>
                <input
                  type="date"
                  disabled={!canManage}
                  min={draft.plannedStart || undefined}
                  value={draft.plannedEnd}
                  onChange={(event) => setDraft({ ...draft, plannedEnd: event.target.value })}
                />
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
                    saveMutation.isPending || !readiness.definitionReady || !definitionDirty
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
            <span className="qms-audit-setup-tile__step" aria-hidden>2</span>
            <span className="qms-audit-setup-tile__title">Audit team</span>
            <span className={`qms-audit-setup-tile__hint${readiness.leadAssigned ? "" : " is-warning"}`}>
              {readiness.leadAssigned ? "Lead auditor assigned" : "Lead auditor required"}
            </span>
            <span className={`qms-audit-setup-tile__state${readiness.leadAssigned ? " is-complete" : " is-required"}`}>
              {readiness.leadAssigned ? "Complete" : "Required"}
            </span>
          </summary>
          <div className="qms-audit-setup-tile__body">
            <AuditAssignmentGovernancePanel amoCode={amoCode} auditKey={auditKey} />
          </div>
        </details>

        <details className="qms-audit-setup-tile" open={openTile === "meetings"}>
          <summary onClick={selectTile("meetings")}>
            <span className="qms-audit-setup-tile__step" aria-hidden>3</span>
            <span className="qms-audit-setup-tile__title">Opening and closing meetings</span>
            <span className="qms-audit-setup-tile__hint">{meetingCount}/2 scheduled</span>
            <span className="qms-audit-setup-tile__state">Governance</span>
          </summary>
          <div className="qms-audit-setup-tile__body">
            {meetingsQuery.isError ? (
              <div className="qms-audit-setup-stage__section-error" role="alert">
                <span>{errorMessage(meetingsQuery.error, "Meetings could not be loaded.")}</span>
                <button type="button" onClick={() => void meetingsQuery.refetch()}>
                  <RefreshCw size={14} /> Retry meetings
                </button>
              </div>
            ) : null}
            {meetingsQuery.isPending ? <p className="qms-audit-setup-stage__empty">Loading meetings…</p> : null}
            {!meetingsQuery.isError && !meetingsQuery.isPending ? (
              <div className="qms-audit-setup-stage__meetings">
                {renderMeeting("OPENING", openingMeeting, openingDraft, setOpeningDraft)}
                {renderMeeting("CLOSING", closingMeeting, closingDraft, setClosingDraft)}
              </div>
            ) : null}
          </div>
        </details>

        <details className="qms-audit-setup-tile" open={openTile === "notice"}>
          <summary onClick={selectTile("notice")}>
            <span className="qms-audit-setup-tile__step" aria-hidden>4</span>
            <span className="qms-audit-setup-tile__title">Audit notice</span>
            <span className="qms-audit-setup-tile__hint">
              {latestNotice ? latestNotice.status.replaceAll("_", " ") : "Not created"}
            </span>
            <span className="qms-audit-setup-tile__state">Governance</span>
          </summary>
          <div className="qms-audit-setup-tile__body">
            {noticesQuery.isError || policiesQuery.isError ? (
              <div className="qms-audit-setup-stage__section-error" role="alert">
                <span>
                  {errorMessage(noticesQuery.error || policiesQuery.error, "Audit notice controls could not be loaded.")}
                </span>
                <button
                  type="button"
                  onClick={() => void Promise.all([noticesQuery.refetch(), policiesQuery.refetch()])}
                >
                  <RefreshCw size={14} /> Retry notice
                </button>
              </div>
            ) : null}
            {noticesQuery.isPending || policiesQuery.isPending ? (
              <p className="qms-audit-setup-stage__empty">Loading notice controls…</p>
            ) : null}
            {!noticesQuery.isError && !policiesQuery.isError && !noticesQuery.isPending && !policiesQuery.isPending && latestNotice ? (
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
            ) : !noticesQuery.isError && !policiesQuery.isError && !noticesQuery.isPending && !policiesQuery.isPending ? (
              <p className="qms-audit-setup-stage__empty">No notice yet.</p>
            ) : null}
            {!noticesQuery.isError && !policiesQuery.isError && !noticesQuery.isPending && !policiesQuery.isPending ? (
              <>
                <div className="qms-audit-notice-summary">
                  <div>
                    <strong>{latestNotice?.artifact?.filename || "System-generated controlled PDF"}</strong>
                    <span>
                      {latestNotice?.artifact?.source_type === "UPLOADED"
                        ? "The attached signed notice will be emailed exactly as previewed."
                        : "The saved audit, meeting and recipient data populate the notice automatically."}
                    </span>
                  </div>
                  <div className="qms-audit-setup-stage__actions">
                    {!latestNotice && canManageNotice ? (
                      <button
                        type="button"
                        className="is-primary"
                        disabled={createNoticeMutation.isPending || noticeReason.trim().length < 8}
                        onClick={() => createNoticeMutation.mutate()}
                      >
                        <CalendarClock size={15} /> Prepare notice preview
                      </button>
                    ) : null}
                    {latestNotice ? (
                      <button
                        type="button"
                        className="is-primary"
                        disabled={previewNoticeMutation.isPending}
                        onClick={() => previewNoticeMutation.mutate(latestNotice)}
                      >
                        <Eye size={15} /> Preview notice
                      </button>
                    ) : null}
                    {latestNotice?.artifact ? (
                      <button
                        type="button"
                        disabled={downloadNoticeMutation.isPending}
                        onClick={() => downloadNoticeMutation.mutate(latestNotice)}
                      >
                        <Download size={15} /> Download PDF
                      </button>
                    ) : null}
                    {latestNotice?.status === "DRAFT" && canManageNotice ? (
                      <label className="qms-audit-notice-upload">
                        <FileUp size={15} /> Attach signed PDF
                        <input
                          type="file"
                          accept="application/pdf,.pdf"
                          disabled={uploadNoticeMutation.isPending}
                          onChange={(event) => {
                            const file = event.currentTarget.files?.[0];
                            event.currentTarget.value = "";
                            if (file) uploadNoticeMutation.mutate({ row: latestNotice, file });
                          }}
                        />
                      </label>
                    ) : null}
                  </div>
                </div>
                {latestNotice && ["DRAFT", "UNDER_REVIEW", "APPROVED", "GENERATED"].includes(latestNotice.status) ? (
                  <p className="qms-audit-notice-guidance">
                    Preview is required before submission. Submission electronically signs the generated PDF, or preserves the attached signed PDF, then sends it with the email notification.
                  </p>
                ) : null}
              </>
            ) : null}
          </div>
        </details>
      </div>

      {noticePreview && previewedNotice ? (
        <div className="qms-audit-notice-modal" role="presentation" onMouseDown={() => setNoticePreview(null)}>
          <section
            className="qms-audit-notice-modal__dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="qms-audit-notice-preview-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <span>Controlled document preview</span>
                <h2 id="qms-audit-notice-preview-title">Audit notice - revision {previewedNotice.revision_no}</h2>
                <small>{noticePreview.filename}</small>
              </div>
              <button type="button" aria-label="Close audit notice preview" onClick={() => setNoticePreview(null)}>
                <X size={18} />
              </button>
            </header>
            <div className="qms-audit-notice-modal__document">
              <iframe src={noticePreview.url} title={`Audit notice revision ${previewedNotice.revision_no} preview`} />
            </div>
            <footer>
              <div className="qms-audit-notice-modal__record">
                <strong>
                  {previewedNotice.artifact?.source_type === "UPLOADED"
                    ? "Attached signed notice"
                    : previewedNotice.artifact
                      ? "Generated and electronically signed notice"
                      : "Generated preview - signature is applied on submission"}
                </strong>
                <span>Status: {previewedNotice.status.replaceAll("_", " ")}</span>
              </div>
              {canManageNotice && ["DRAFT", "UNDER_REVIEW", "APPROVED", "GENERATED"].includes(previewedNotice.status) ? (
                <label className="qms-audit-notice-modal__reason">
                  <span>Issuance record note</span>
                  <textarea rows={2} value={noticeReason} onChange={(event) => setNoticeReason(event.target.value)} />
                </label>
              ) : null}
              <div className="qms-audit-notice-modal__actions">
                <button type="button" onClick={() => setNoticePreview(null)}>Close</button>
                {previewedNotice.artifact ? (
                  <button type="button" disabled={downloadNoticeMutation.isPending} onClick={() => downloadNoticeMutation.mutate(previewedNotice)}>
                    <Download size={15} /> Download PDF
                  </button>
                ) : null}
                {canManageNotice && ["DRAFT", "UNDER_REVIEW", "APPROVED", "GENERATED"].includes(previewedNotice.status) ? (
                  <button
                    type="button"
                    className="is-primary"
                    disabled={submitNoticeMutation.isPending || noticeReason.trim().length < 8}
                    onClick={() => submitNoticeMutation.mutate(previewedNotice)}
                  >
                    <Send size={15} /> {previewedNotice.status === "GENERATED" ? "Retry email delivery" : "Submit and email notice"}
                  </button>
                ) : null}
              </div>
            </footer>
          </section>
        </div>
      ) : null}
    </section>
  );
};

export default AuditSetupWorkspace;
