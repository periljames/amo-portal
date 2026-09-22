import React, { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CalendarClock, CheckCircle2, Download, ExternalLink, Eye, FileUp, RefreshCw, Save, Send, Video, X } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { type QMSAuditOut } from "../../../services/qms";
import {
  createAuditNotice,
  downloadAuditNoticeDocument,
  getAuditNoticeTemplate,
  listAuditNotices,
  listAuditNoticePolicies,
  prepareAuditNoticeDocument,
  previewAuditNoticePdf,
  submitAuditNotice,
  updateAuditNoticeTemplate,
  uploadAuditNoticeAttachment,
  type AuditNotice,
} from "../../../services/qmsAuditGovernance";
import { downloadBlob } from "../../../services/typedApi";
import {
  createAuditMeeting,
  deleteAuditMeeting,
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
import { useSavedAuditTeam } from "./useSavedAuditTeam";
import { meetingTimelineIssue, setupDateLabel, reconcileSetupDraft, normalizeMeetingWindow, normalizePlannedAuditWindow } from "./auditSetupControls";
import { auditNoticePeriodInsufficient } from "./auditNoticePeriod";
import {
  auditMeetingSubject,
  isTeamsMeetingUrl,
  teamsCreateMeetingUrl,
} from "./auditMeetingConnect";
import AuditNoticePdfPreview from "./AuditNoticePdfPreview";
import { AuditStageLoadError } from "./AuditStageLoadError";
import { auditSetupIssues, auditSetupReadiness, type AuditSetupFieldId } from "./auditSetupModel";
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
  plannedStartTime: string;
  plannedEndTime: string;
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

const MODALITY_OPTIONS: Array<{ value: Exclude<MeetingModality, "">; label: string; hint: string }> = [
  { value: "PHYSICAL", label: "On site", hint: "Room / facility only" },
  { value: "ONLINE", label: "Teams", hint: "Online meeting link" },
  { value: "HYBRID", label: "Hybrid", hint: "On site + Teams" },
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

function formatPlannedWindow(dateValue: string, timeValue: string): string {
  const day = formatPlannedDisplay(dateValue);
  return day === "—" ? day : setupDateLabel(`${day}T${timeValue || "00:00"}`);
}

function shiftTime(value: string, minutes: number): string {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) return "";
  const total = Math.max(0, Math.min(23 * 60 + 59, Number(match[1]) * 60 + Number(match[2]) + minutes));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function inheritedMeetingWindow(
  type: "OPENING" | "CLOSING",
  plannedStart: string,
  plannedEnd: string,
  plannedStartTime = "09:00",
  plannedEndTime = "17:00",
): { start: string; end: string } {
  const day = datePart(type === "OPENING" ? plannedStart : plannedEnd);
  if (!day) return { start: "", end: "" };
  const openingEnd = plannedStartTime || OPENING_MEETING_END;
  const closingStart = plannedEndTime || CLOSING_MEETING_START;
  return type === "OPENING"
    ? { start: `${day}T${shiftTime(openingEnd, -60) || OPENING_MEETING_START}`, end: `${day}T${openingEnd}` }
    : { start: `${day}T${closingStart}`, end: `${day}T${shiftTime(closingStart, 60) || CLOSING_MEETING_END}` };
}

function inferModality(location: string | null | undefined, conferenceUrl: string | null | undefined): MeetingModality {
  const locationText = (location || "").trim();
  const locationKey = locationText.toLowerCase();
  const hasLocation = Boolean(locationText) && locationKey !== "online" && locationKey !== "teams";
  const hasUrl = Boolean((conferenceUrl || "").trim());
  if (hasLocation && hasUrl) return "HYBRID";
  if (hasUrl || locationKey === "online" || locationKey === "teams") return "ONLINE";
  if (hasLocation) return "PHYSICAL";
  return "";
}

function meetingDraftFromRow(
  row: AuditMeeting | null,
  type: "OPENING" | "CLOSING",
  plannedStart: string,
  plannedEnd: string,
  plannedStartTime: string,
  plannedEndTime: string,
  timezoneName?: string,
): MeetingDraft {
  const inherited = inheritedMeetingWindow(type, plannedStart, plannedEnd, plannedStartTime, plannedEndTime);
  if (!row) {
    return {
      ...emptyMeeting,
      ...inherited,
    };
  }
  const originalStart = localDateTime(row.scheduled_start, timezoneName);
  const originalEnd = localDateTime(row.scheduled_end, timezoneName);
  const now = localDateTime(new Date(Date.now() + 60_000).toISOString(), timezoneName);
  const { start, end } = row.status === "PLANNED"
    ? normalizeMeetingWindow(originalStart, originalEnd, now, type === "CLOSING" ? inherited.start : now)
    : { start: originalStart, end: originalEnd };
  const matchesDefinition =
    Boolean(inherited.start) && start === inherited.start && (!end || !inherited.end || end === inherited.end);
  const modality = inferModality(row.location, row.conference_url);
  const locationText = (row.location || "").trim();
  const locationKey = locationText.toLowerCase();
  return {
    modality,
    customSchedule: !matchesDefinition,
    start,
    end,
    location:
      modality === "ONLINE" || locationKey === "online" || locationKey === "teams"
        ? ""
        : locationText,
    conferenceUrl: row.conference_url || "",
  };
}

function meetingReady(
  type: "OPENING" | "CLOSING",
  value: MeetingDraft,
  plannedStart: string,
  plannedEnd: string,
  plannedStartTime: string,
  plannedEndTime: string,
): boolean {
  if (!value.modality) return false;
  const inherited = inheritedMeetingWindow(type, plannedStart, plannedEnd, plannedStartTime, plannedEndTime);
  const start = value.customSchedule ? value.start : inherited.start;
  const end = value.customSchedule ? value.end : inherited.end;
  if (!start || !end) return false;
  if (end < start) return false;
  if ((value.modality === "PHYSICAL" || value.modality === "HYBRID") && !value.location.trim()) return false;
  // Teams/hybrid links can be pasted after the meeting is scheduled.
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
    plannedStartTime: (audit.planned_start_time || "09:00").slice(0, 5),
    plannedEndTime: (audit.planned_end_time || "17:00").slice(0, 5),
    notifyAuditors: audit.notify_auditors !== false,
    notifyAuditees: audit.notify_auditees !== false,
    reminderIntervalDays: String(audit.reminder_interval_days || 7),
  };
}

function draftFromAuditReady(audit: QMSAuditOut, nowLocal?: string): SetupDraft {
  const base = draftFromAudit(audit);
  const floor = nowLocal || localDateTime(new Date(Date.now() + 60_000).toISOString());
  const normalized = normalizePlannedAuditWindow(
    base.plannedStart ? `${base.plannedStart}T${base.plannedStartTime}` : "",
    base.plannedEnd ? `${base.plannedEnd}T${base.plannedEndTime}` : "",
    floor,
  );
  return { ...base, ...normalized };
}

function localDateTime(value?: string | null, timeZone?: string): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  if (timeZone) {
    try {
      const parts = new Intl.DateTimeFormat("en-CA", {
        timeZone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }).formatToParts(parsed);
      const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value || "";
      return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
    } catch {
      // Fall back to the browser timezone if the tenant timezone is not available.
    }
  }
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
  const [teamDirty, setTeamDirty] = useState(false);
  const [currentTime, setCurrentTime] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setCurrentTime(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const savedDefinitionRef = useRef<{ id: string; draft: SetupDraft } | null>(null);
  const savedOpeningRef = useRef<{ id: string; draft: MeetingDraft } | null>(null);
  const savedClosingRef = useRef<{ id: string; draft: MeetingDraft } | null>(null);
  const [openingDraft, setOpeningDraft] = useState<MeetingDraft>(emptyMeeting);
  const [closingDraft, setClosingDraft] = useState<MeetingDraft>(emptyMeeting);
  const [openTile, setOpenTile] = useState<SetupTileId | null>("definition");
  const [noticeReason, setNoticeReason] = useState("Final audit notice generated for review before controlled email delivery.");
  const [shortNoticeWaiverReason, setShortNoticeWaiverReason] = useState("");
  const [noticePreview, setNoticePreview] = useState<{ url: string; blob: Blob; filename: string; notice: AuditNotice } | null>(null);
  const [guidedField, setGuidedField] = useState<AuditSetupFieldId | null>(null);
  const guidanceRequestHandled = useRef<string | null>(null);
  const guidanceActive = useRef<AuditSetupFieldId | null>(null);
  const retrievalNoticeHandled = useRef<string | null>(null);
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
  const savedTeam = useSavedAuditTeam(amoCode, auditQuery.data);

  useEffect(() => {
    const hash = location.hash.replace(/^#/, "");
    if (!hash || hash === "setup-required") return;
    const frame = window.requestAnimationFrame(() => {
      if (hash === "team" || hash === "team-wrap") setOpenTile("team");
      if (hash === "overview") setOpenTile("definition");
      if (hash === "notice") setOpenTile("notice");
      document.getElementById(`audit-occurrence-${hash}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [location.hash, auditQuery.isSuccess]);

  const setupIssues = useMemo(
    () => draft
      ? auditSetupIssues({
          ...draft,
          leadAuditorUserId: auditQuery.data?.lead_auditor_user_id,
        })
      : [],
    [draft, auditQuery.data?.lead_auditor_user_id],
  );

  const showRequiredField = (field: AuditSetupFieldId, tile: SetupTileId) => {
    guidanceActive.current = field;
    setGuidedField(field);
    setOpenTile(tile);
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        if (guidanceActive.current !== field) return;
        document.getElementById(`audit-setup-field-${field}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    });
  };

  useEffect(() => {
    if (!draft || !auditId) return;
    const search = new URLSearchParams(location.search);
    if (search.get("setupRequired") !== "1") return;
    const requestKey = `${auditId}:${location.search}`;
    if (guidanceRequestHandled.current === requestKey) return;
    guidanceRequestHandled.current = requestKey;
    const requested = search.get("required") as AuditSetupFieldId | null;
    const issue = setupIssues.find((item) => item.field === requested) || setupIssues[0];
    if (!issue) return;
    const frame = window.requestAnimationFrame(() => showRequiredField(issue.field, issue.tile));
    return () => window.cancelAnimationFrame(frame);
  }, [auditId, draft, location.search, setupIssues]);

  const clearGuidance = (field: AuditSetupFieldId) => {
    if (guidanceActive.current !== field) return;
    guidanceActive.current = null;
    setGuidedField(null);
  };

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
  const templateQuery = useQuery({
    queryKey: ["qms-audit-notice-template", amoCode],
    queryFn: ({ signal }) => getAuditNoticeTemplate(amoCode, signal),
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
      const now = localDateTime(new Date(currentTime + 60_000).toISOString(), meetingsQuery.data?.timezone_name);
      const incoming = draftFromAuditReady(row, now);
      const previous = savedDefinitionRef.current?.id === row.id ? savedDefinitionRef.current.draft : null;
      setDraft((current) => reconcileSetupDraft(current, previous, incoming));
      savedDefinitionRef.current = { id: row.id, draft: incoming };
      if (JSON.stringify(incoming) !== JSON.stringify(draftFromAudit(row))) {
        setNotice("Past audit dates were reset to the next available window. Save the definition to keep them.");
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [auditQuery.data, meetingsQuery.data?.timezone_name]);
  useEffect(() => {
    const plannedStart = datePart(auditQuery.data?.planned_start || "");
    const plannedEnd = datePart(auditQuery.data?.planned_end || "");
    const plannedStartTime = (auditQuery.data?.planned_start_time || "09:00").slice(0, 5);
    const plannedEndTime = (auditQuery.data?.planned_end_time || "17:00").slice(0, 5);
    const frame = window.requestAnimationFrame(() => {
      const incoming = meetingDraftFromRow(openingMeeting, "OPENING", plannedStart, plannedEnd, plannedStartTime, plannedEndTime, meetingsQuery.data?.timezone_name);
      const previous = savedOpeningRef.current?.id === auditId ? savedOpeningRef.current.draft : null;
      setOpeningDraft((current) => reconcileSetupDraft(current, previous, incoming));
      savedOpeningRef.current = { id: auditId, draft: incoming };
    });
    return () => window.cancelAnimationFrame(frame);
  }, [auditId, openingMeeting, auditQuery.data?.planned_start, auditQuery.data?.planned_end, auditQuery.data?.planned_start_time, auditQuery.data?.planned_end_time, meetingsQuery.data?.timezone_name]);
  useEffect(() => {
    const plannedStart = datePart(auditQuery.data?.planned_start || "");
    const plannedEnd = datePart(auditQuery.data?.planned_end || "");
    const plannedStartTime = (auditQuery.data?.planned_start_time || "09:00").slice(0, 5);
    const plannedEndTime = (auditQuery.data?.planned_end_time || "17:00").slice(0, 5);
    const frame = window.requestAnimationFrame(() => {
      const incoming = meetingDraftFromRow(closingMeeting, "CLOSING", plannedStart, plannedEnd, plannedStartTime, plannedEndTime, meetingsQuery.data?.timezone_name);
      const previous = savedClosingRef.current?.id === auditId ? savedClosingRef.current.draft : null;
      setClosingDraft((current) => reconcileSetupDraft(current, previous, incoming));
      savedClosingRef.current = { id: auditId, draft: incoming };
    });
    return () => window.cancelAnimationFrame(frame);
  }, [auditId, closingMeeting, auditQuery.data?.planned_start, auditQuery.data?.planned_end, auditQuery.data?.planned_start_time, auditQuery.data?.planned_end_time, meetingsQuery.data?.timezone_name]);

  // Keep inherited schedules aligned with Definition dates while custom schedule is off.
  // Snap past inherited opening windows to now so operators never keep impossible times.
  const inheritedPlannedStart = draft?.plannedStart;
  const inheritedPlannedEnd = draft?.plannedEnd;
  const inheritedPlannedStartTime = draft?.plannedStartTime;
  const inheritedPlannedEndTime = draft?.plannedEndTime;
  useEffect(() => {
    if (inheritedPlannedStart === undefined || inheritedPlannedEnd === undefined || inheritedPlannedStartTime === undefined || inheritedPlannedEndTime === undefined) return;
    const frame = window.requestAnimationFrame(() => {
      const now = localDateTime(new Date(currentTime + 60_000).toISOString(), meetingsQuery.data?.timezone_name);
      const openingInherited = inheritedMeetingWindow("OPENING", inheritedPlannedStart, inheritedPlannedEnd, inheritedPlannedStartTime, inheritedPlannedEndTime);
      const closingInherited = inheritedMeetingWindow("CLOSING", inheritedPlannedStart, inheritedPlannedEnd, inheritedPlannedStartTime, inheritedPlannedEndTime);
      const openingWindow = normalizeMeetingWindow(openingInherited.start, openingInherited.end, now);
      const closingWindow = normalizeMeetingWindow(closingInherited.start, closingInherited.end, now, closingInherited.start);
      setOpeningDraft((current) => (current.customSchedule ? current : { ...current, ...openingWindow }));
      setClosingDraft((current) => (current.customSchedule ? current : { ...current, ...closingWindow }));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [inheritedPlannedStart, inheritedPlannedEnd, inheritedPlannedStartTime, inheritedPlannedEndTime, meetingsQuery.data?.timezone_name]);

  const correctDefinitionDates = () => {
    if (!draft) return;
    const now = localDateTime(new Date(currentTime + 60_000).toISOString(), meetingsQuery.data?.timezone_name);
    const normalized = normalizePlannedAuditWindow(
      `${draft.plannedStart}T${draft.plannedStartTime}`,
      `${draft.plannedEnd}T${draft.plannedEndTime}`,
      now,
    );
    const next = { ...draft, ...normalized };
    if (JSON.stringify(next) !== JSON.stringify(draft)) {
      setDraft(next);
      setNotice("Dates adjusted to the next available audit time. Save the definition to apply.");
    }
  };

  const selectTile = (tile: SetupTileId) => (event: React.MouseEvent<HTMLElement>) => {
    event.preventDefault();
    setOpenTile((current) => current === tile ? null : tile);
  };

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: auditOccurrenceQueryKey(amoCode, auditKey) }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-notices", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-meetings", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-notice-template", amoCode] }),
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
        planned_start_time: draft.plannedStartTime || null,
        planned_end_time: draft.plannedEndTime || null,
        notify_auditors: draft.notifyAuditors,
        notify_auditees: draft.notifyAuditees,
        reminder_interval_days: Math.max(1, Math.min(60, Number(draft.reminderIntervalDays) || 7)),
      });
    },
    onSuccess: async (row) => {
      const now = localDateTime(new Date(currentTime + 60_000).toISOString(), meetingsQuery.data?.timezone_name);
      setDraft(draftFromAuditReady(row, now));
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
      const inherited = inheritedMeetingWindow(type, draft.plannedStart, draft.plannedEnd, draft.plannedStartTime, draft.plannedEndTime);
      const start = value.customSchedule ? value.start : inherited.start;
      const end = value.customSchedule ? value.end : inherited.end;
      if (!start) throw new Error(`${type === "OPENING" ? "Opening" : "Closing"} meeting start is required.`);
      if (!end) throw new Error(`${type === "OPENING" ? "Opening" : "Closing"} meeting end is required.`);
      const now = localDateTime(new Date(currentTime + 60_000).toISOString(), meetingsQuery.data?.timezone_name);
      const snapped = normalizeMeetingWindow(start, end, now, type === "CLOSING" ? inherited.start : now);
      const timelineIssue = meetingTimelineIssue(type, snapped.start, snapped.end, `${draft.plannedStart}T${draft.plannedStartTime}`, `${draft.plannedEnd}T${draft.plannedEndTime}`, now);
      if (timelineIssue) throw new Error(timelineIssue);
      if ((value.modality === "PHYSICAL" || value.modality === "HYBRID") && !value.location.trim()) {
        throw new Error("Physical location is required for this meeting modality.");
      }
      const conferenceUrl = value.conferenceUrl.trim();
      // Persist an Online/Teams marker so modality survives reload before the join link is pasted.
      const location =
        value.modality === "ONLINE"
          ? conferenceUrl
            ? null
            : "Online"
          : value.location.trim() || null;
      const payload = {
        meeting_type: type,
        scheduled_start: snapped.start,
        scheduled_end: snapped.end,
        location,
        conference_url: value.modality === "PHYSICAL" ? null : conferenceUrl || null,
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

  const removeMeetingMutation = useMutation({
    mutationFn: (row: AuditMeeting) => deleteAuditMeeting(amoCode, auditId, row.id),
    onSuccess: async () => { setNotice("Meeting deleted."); await refresh(); },
    onError: (cause) => setLocalError(errorMessage(cause, "Meeting could not be deleted.")),
  });

  const previewNoticeMutation = useMutation({
    mutationFn: async (row: AuditNotice) => {
      const waiver = shortNoticeWaiverReason.trim();
      const prepared = row.artifact
        ? row
        : await prepareAuditNoticeDocument(amoCode, auditId, row.id, noticeReason.trim(), {
            shortNoticeWaiverReason: waiver || undefined,
          });
      const preview = await previewAuditNoticePdf(amoCode, auditId, prepared.id);
      return { row: prepared, ...preview };
    },
    onSuccess: ({ row, blob, filename }) => {
      setLocalError(null);
      setNoticePreview({
        url: URL.createObjectURL(blob),
        blob,
        filename: filename || row.artifact?.filename || `audit-notice-r${row.revision_no}.pdf`,
        notice: row,
      });
      void queryClient.invalidateQueries({ queryKey: ["qms-audit-notices", amoCode, auditId] });
    },
    onError: (cause) => setLocalError(errorMessage(cause, "The final signed audit notice could not be prepared.")),
  });

  const createNoticeMutation = useMutation({
    mutationFn: async () => {
      if (!auditQuery.data || !draft) throw new Error("Save the audit occurrence before creating its notice.");
      const policy =
        policiesQuery.data?.items.find((item) => !item.audit_kind || item.audit_kind === auditQuery.data?.kind) ||
        policiesQuery.data?.items[0];
      return createAuditNotice(amoCode, auditId, {
        policy_id: policy?.id,
        template_document_id: templateQuery.data?.selected_document_id || undefined,
        notice_date: new Date().toISOString().slice(0, 10),
        exception_reason: shortNoticeWaiverReason.trim() || undefined,
        reason: noticeReason.trim(),
      });
    },
    onSuccess: async () => {
      setLocalError(null);
      setNotice("Notice draft prepared from the saved audit data. Generate the final signed preview when ready.");
      await refresh();
    },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Audit notice could not be created."),
  });

  const templateMutation = useMutation({
    mutationFn: (documentId: string) => updateAuditNoticeTemplate(amoCode, documentId),
    onSuccess: async () => {
      setLocalError(null);
      setNotice("Tenant audit notice form updated. The current published DMS revision will be used.");
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-notice-template", amoCode] });
    },
    onError: (cause) => setLocalError(errorMessage(cause, "The audit notice form could not be updated.")),
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
    mutationFn: (row: AuditNotice) =>
      submitAuditNotice(amoCode, auditId, row.id, noticeReason.trim(), {
        shortNoticeWaiverReason: shortNoticeWaiverReason.trim() || undefined,
      }),
    onSuccess: async (result) => {
      setLocalError(null);
      setNotice(
        result.delivery_complete
          ? `The exact previewed notice was sent as a PDF attachment to ${result.dispatch.sent} email${result.dispatch.sent === 1 ? "" : "s"}.`
          : `The notice PDF is ready, but ${result.dispatch.failed} of ${result.dispatch.attempted} email deliveries failed. Correct the email configuration and retry.`,
      );
      setNoticePreview((current) => current ? { ...current, notice: result.notice } : current);
      await refresh();
    },
    onError: (cause) => setLocalError(errorMessage(cause, "The audit notice could not be submitted.")),
  });

  const downloadNoticeMutation = useMutation({
    mutationFn: async (row: AuditNotice) => ({ row, ...(await downloadAuditNoticeDocument(amoCode, auditId, row.id)) }),
    onSuccess: ({ row, blob, filename }) => downloadBlob(blob, filename || row.artifact?.filename || "audit-notice.pdf"),
    onError: (cause) => setLocalError(errorMessage(cause, "The audit notice PDF could not be downloaded.")),
  });

  useEffect(() => {
    const noticeId = new URLSearchParams(location.search).get("noticeId");
    if (!noticeId || !auditId) return;
    const row = noticesQuery.data?.items.find((item) => item.id === noticeId);
    if (!row?.artifact) return;
    const requestKey = `${auditId}:${noticeId}`;
    if (retrievalNoticeHandled.current === requestKey) return;
    retrievalNoticeHandled.current = requestKey;
    const frame = window.requestAnimationFrame(() => {
      setOpenTile("notice");
      previewNoticeMutation.mutate(row);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [auditId, location.search, noticesQuery.data?.items, previewNoticeMutation]);

  const latestNotice = useMemo(
    () => (noticesQuery.data?.items || []).slice().sort((a, b) => b.revision_no - a.revision_no)[0] || null,
    [noticesQuery.data?.items],
  );
  const previewedNotice = noticePreview?.notice || null;

  /* Mirror the saved notice waiver reason into the editable draft when the governed notice changes. */
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (latestNotice?.exception_reason) {
      setShortNoticeWaiverReason(latestNotice.exception_reason);
    }
  }, [latestNotice?.id, latestNotice?.exception_reason]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const activeNoticePolicy =
    policiesQuery.data?.items.find(
      (item) => !item.audit_kind || item.audit_kind === auditQuery.data?.kind,
    ) || policiesQuery.data?.items[0];
  const requiredNoticeDays =
    latestNotice?.required_notice_days ??
    activeNoticePolicy?.minimum_notice_days ??
    14;
  const noticeDateForPeriod =
    latestNotice?.notice_date || new Date().toISOString().slice(0, 10);
  const noticePeriodShort = auditNoticePeriodInsufficient({
    plannedStart: draft?.plannedStart || auditQuery.data?.planned_start,
    noticeDate: noticeDateForPeriod,
    requiredNoticeDays,
  });
  const shortNoticeWaiverReady =
    !noticePeriodShort ||
    shortNoticeWaiverReason.trim().length >= 8 ||
    Boolean(latestNotice?.exception_reason && latestNotice.exception_reason.trim().length >= 8);

  if (auditQuery.isLoading && !auditQuery.data) {
    return <section className="qms-occurrence-stage qms-occurrence-stage--loading">Loading audit setup…</section>;
  }
  if (!auditQuery.data) {
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
  const setupReady = readiness.ready && savedTeam.ready && !definitionDirty && !teamDirty;
  const guidedIssue = guidedField ? setupIssues.find((item) => item.field === guidedField) : null;
  const guidedClass = (field: AuditSetupFieldId) => guidedField === field ? "is-guided-required" : undefined;
  const supportingErrorCount = [meetingsQuery.error, noticesQuery.error, policiesQuery.error, templateQuery.error].filter(Boolean).length;

  const scheduleMeetingPair = async (modality: Exclude<MeetingModality, "">) => {
    if (definitionDirty) {
      setLocalError("Save the audit definition before scheduling meetings.");
      return;
    }
    const openingInherited = inheritedMeetingWindow(
      "OPENING",
      draft.plannedStart,
      draft.plannedEnd,
      draft.plannedStartTime,
      draft.plannedEndTime,
    );
    const closingInherited = inheritedMeetingWindow(
      "CLOSING",
      draft.plannedStart,
      draft.plannedEnd,
      draft.plannedStartTime,
      draft.plannedEndTime,
    );
    const openingValue: MeetingDraft = {
      modality,
      customSchedule: false,
      start: openingInherited.start,
      end: openingInherited.end,
      location: modality === "ONLINE" ? "" : openingDraft.location || "",
      conferenceUrl: modality === "PHYSICAL" ? "" : openingDraft.conferenceUrl || "",
    };
    const closingValue: MeetingDraft = {
      modality,
      customSchedule: false,
      start: closingInherited.start,
      end: closingInherited.end,
      location: modality === "ONLINE" ? "" : closingDraft.location || "",
      conferenceUrl: modality === "PHYSICAL" ? "" : closingDraft.conferenceUrl || "",
    };
    if (modality !== "ONLINE" && !openingValue.location.trim()) {
      openingValue.location = "Main base";
      closingValue.location = openingValue.location;
    }
    setOpeningDraft(openingValue);
    setClosingDraft(closingValue);
    try {
      await meetingMutation.mutateAsync({
        type: "OPENING",
        row: openingMeeting,
        value: openingValue,
      });
      await meetingMutation.mutateAsync({
        type: "CLOSING",
        row: closingMeeting,
        value: closingValue,
      });
      setLocalError(null);
      setNotice(
        modality === "ONLINE" || modality === "HYBRID"
          ? "Opening and closing meetings scheduled. Connect Teams and paste the join links."
          : "Opening and closing meetings scheduled.",
      );
      setOpenTile("meetings");
    } catch (cause) {
      setLocalError(
        cause instanceof Error ? cause.message : "Meetings could not be scheduled.",
      );
    }
  };

  const renderMeeting = (
    type: "OPENING" | "CLOSING",
    row: AuditMeeting | null,
    value: MeetingDraft,
    setValue: React.Dispatch<React.SetStateAction<MeetingDraft>>,
  ) => {
    const needsLocation = value.modality === "PHYSICAL" || value.modality === "HYBRID";
    const needsUrl = value.modality === "ONLINE" || value.modality === "HYBRID";
    const inherited = inheritedMeetingWindow(
      type,
      draft.plannedStart,
      draft.plannedEnd,
      draft.plannedStartTime,
      draft.plannedEndTime,
    );
    const effectiveStart = value.customSchedule ? value.start : inherited.start;
    const effectiveEnd = value.customSchedule ? value.end : inherited.end;
    const timelineIssue = meetingTimelineIssue(
      type,
      effectiveStart,
      effectiveEnd,
      `${draft.plannedStart}T${draft.plannedStartTime}`,
      `${draft.plannedEnd}T${draft.plannedEndTime}`,
      localDateTime(
        new Date(currentTime + 60_000).toISOString(),
        meetingsQuery.data?.timezone_name,
      ),
    );
    const teamsSubject = auditMeetingSubject(
      type,
      auditQuery.data?.title,
      auditQuery.data?.audit_ref,
    );
    const teamsHref = teamsCreateMeetingUrl({
      subject: teamsSubject,
      start: effectiveStart,
      end: effectiveEnd,
    });
    const teamsLinked = isTeamsMeetingUrl(value.conferenceUrl);
    const canSave =
      !definitionDirty &&
      !timelineIssue &&
      meetingReady(
        type,
        value,
        draft.plannedStart,
        draft.plannedEnd,
        draft.plannedStartTime,
        draft.plannedEndTime,
      ) &&
      !meetingMutation.isPending;

    return (
      <div className={`qms-audit-setup-stage__meeting${row ? " is-saved" : ""}`}>
        <header className="qms-audit-setup-stage__meeting-head">
          <div>
            <strong>{type === "OPENING" ? "Opening" : "Closing"}</strong>
            <small>
              {row
                ? row.status.replaceAll("_", " ")
                : "Not saved"}{" "}
              · {meetingsQuery.data?.timezone_name || "tenant local time"}
            </small>
          </div>
          {row ? (
            <span className="qms-audit-setup-stage__meeting-pill is-complete">Saved</span>
          ) : (
            <span className="qms-audit-setup-stage__meeting-pill">Draft</span>
          )}
        </header>

        <div className="qms-audit-setup-stage__modality-seg" role="group" aria-label={`${type} format`}>
          {MODALITY_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={value.modality === option.value ? "is-active" : ""}
              disabled={!canManage}
              title={option.hint}
              onClick={() =>
                setValue((current) => ({
                  ...current,
                  modality: option.value,
                  location: option.value === "ONLINE" ? "" : current.location,
                  conferenceUrl:
                    option.value === "PHYSICAL" ? "" : current.conferenceUrl,
                }))
              }
            >
              {option.label}
            </button>
          ))}
        </div>

        {!value.modality ? (
          <p className="qms-audit-setup-stage__empty">Choose a format to continue.</p>
        ) : (
          <>
            <div className="qms-audit-setup-stage__schedule-bar">
              <p className="qms-audit-setup-stage__schedule-inherit">
                {value.customSchedule ? "Custom schedule" : "From audit dates"}:{" "}
                <strong>{effectiveStart.replace("T", " ") || "Set audit dates first"}</strong>
                {effectiveEnd ? (
                  <>
                    {" "}
                    → <strong>{effectiveEnd.replace("T", " ")}</strong>
                  </>
                ) : null}
              </p>
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
                      start: customSchedule
                        ? current.start || inherited.start
                        : inherited.start,
                      end: customSchedule ? current.end || inherited.end : inherited.end,
                    }));
                  }}
                />
                Customize
              </label>
            </div>

            {value.customSchedule ? (
              <div className="qms-audit-setup-stage__fields">
                <label>
                  <span>Start</span>
                  <input
                    type="datetime-local"
                    min={localDateTime(
                      new Date(currentTime + 60_000).toISOString(),
                      meetingsQuery.data?.timezone_name,
                    )}
                    onBlur={() =>
                      setValue((current) => ({
                        ...current,
                        ...normalizeMeetingWindow(
                          current.start,
                          current.end,
                          localDateTime(
                            new Date(currentTime + 60_000).toISOString(),
                            meetingsQuery.data?.timezone_name,
                          ),
                          type === "CLOSING" ? inherited.start : undefined,
                        ),
                      }))
                    }
                    disabled={!canManage}
                    value={value.start}
                    onChange={(event) =>
                      setValue((current) => ({
                        ...current,
                        start: event.target.value,
                      }))
                    }
                  />
                </label>
                <label>
                  <span>End</span>
                  <input
                    type="datetime-local"
                    min={localDateTime(
                      new Date(currentTime + 60_000).toISOString(),
                      meetingsQuery.data?.timezone_name,
                    )}
                    onBlur={() =>
                      setValue((current) => ({
                        ...current,
                        ...normalizeMeetingWindow(
                          current.start,
                          current.end,
                          localDateTime(
                            new Date(currentTime + 60_000).toISOString(),
                            meetingsQuery.data?.timezone_name,
                          ),
                          type === "CLOSING" ? inherited.start : undefined,
                        ),
                      }))
                    }
                    disabled={!canManage}
                    value={value.end}
                    onChange={(event) =>
                      setValue((current) => ({
                        ...current,
                        end: event.target.value,
                      }))
                    }
                  />
                </label>
              </div>
            ) : null}

            <div className="qms-audit-setup-stage__fields">
              {needsLocation ? (
                <label>
                  <span>Location</span>
                  <input
                    disabled={!canManage}
                    value={value.location}
                    onChange={(event) =>
                      setValue((current) => ({
                        ...current,
                        location: event.target.value,
                      }))
                    }
                    placeholder="Room / facility"
                  />
                </label>
              ) : null}
              {needsUrl ? (
                <label className="qms-audit-setup-stage__teams-field">
                  <span>Teams / conference link</span>
                  <input
                    type="url"
                    disabled={!canManage}
                    value={value.conferenceUrl}
                    onChange={(event) =>
                      setValue((current) => ({
                        ...current,
                        conferenceUrl: event.target.value,
                      }))
                    }
                    placeholder="Paste Teams join URL"
                  />
                  <div className="qms-audit-setup-stage__teams-actions">
                    <a
                      className="qms-audit-setup-stage__teams-link"
                      href={teamsHref}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <Video size={14} /> Open Teams
                      <ExternalLink size={13} aria-hidden />
                    </a>
                    {teamsLinked ? (
                      <span className="qms-audit-setup-stage__teams-ok">Teams link ready</span>
                    ) : (
                      <small>Create in Teams, then paste the join link here.</small>
                    )}
                  </div>
                </label>
              ) : null}
            </div>

            {definitionDirty ? (
              <p role="status">Save the audit dates before updating meetings.</p>
            ) : null}
            {timelineIssue ? (
              <p className="qms-occurrence-stage__message is-error" role="alert">
                {timelineIssue}
              </p>
            ) : null}
            {canManage ? (
              <div className="qms-audit-setup-stage__actions">
                <button
                  type="button"
                  className="is-primary"
                  disabled={!canSave}
                  onClick={() => meetingMutation.mutate({ type, row, value })}
                >
                  <Save size={15} /> {row ? "Update meeting" : "Save meeting"}
                </button>
                {row ? (
                  <button
                    type="button"
                    disabled={
                      removeMeetingMutation.isPending || meetingMutation.isPending
                    }
                    onClick={() => {
                      if (window.confirm("Delete this meeting?")) {
                        removeMeetingMutation.mutate(row);
                      }
                    }}
                  >
                    Delete
                  </button>
                ) : null}
              </div>
            ) : null}
          </>
        )}
      </div>
    );
  };

  const meetingCount = [openingMeeting, closingMeeting].filter(Boolean).length;
  const definitionSummary = [
    draft.title,
    draft.plannedStart && draft.plannedEnd
      ? `${formatPlannedWindow(draft.plannedStart, draft.plannedStartTime)} → ${formatPlannedWindow(draft.plannedEnd, draft.plannedEndTime)}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const selectedTemplateId = latestNotice?.template_document_id || templateQuery.data?.selected_document_id || "";
  const selectedTemplate = templateQuery.data?.items.find((item) => item.document_id === selectedTemplateId);

  return (
    <section className="qms-occurrence-stage qms-audit-setup-stage" aria-label="Audit setup workspace" id="audit-occurrence-overview">
      {auditQuery.isError ? <div className="qms-audit-setup-stage__supporting-warning" role="status">Showing the saved audit record. Live updates are unavailable; your edits are retained. <button type="button" onClick={() => void auditQuery.refetch()}>Retry</button></div> : null}
      <div className="qms-audit-setup-stage__toolbar">
        <div className="qms-audit-setup-stage__intro">
          <h2 className="qms-audit-setup-stage__title">Setup</h2>
          <p className="qms-audit-setup-stage__helper">
            Complete the required definition and lead-auditor steps first. Meetings and notice can then be prepared here.
          </p>
          <div className="qms-audit-setup-stage__status" role="status" aria-label="Setup status">
            <span className={`qms-audit-setup-stage__chip${readiness.definitionReady ? "" : " is-warning"}`}>
              Definition {definitionDirty ? "unsaved" : readiness.definitionReady ? "saved" : "incomplete"}
            </span>
            <span className={`qms-audit-setup-stage__chip${teamDirty || !savedTeam.ready ? " is-warning" : ""}`}>
              Team {teamDirty ? "unsaved" : savedTeam.ready ? "verified" : "needs review"}
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
              Open Prepare
              <ArrowRight size={16} aria-hidden />
            </Link>
          ) : (
            <button
              type="button"
              className="qms-occurrence-stage__next"
              disabled
              title={definitionDirty ? "Save the audit definition before continuing." : readiness.issues.join(" ")}
            >
              Open Prepare
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
          <strong>{setupReady ? "Setup ready" : "Complete setup before Prepare"}</strong>
          {!setupReady ? (
            <p>
              {definitionDirty
                ? "Save the audit definition before continuing."
                : teamDirty
                  ? "Save or discard team changes before continuing."
                  : readiness.issues.length
                    ? readiness.issues.join(" ")
                    : savedTeam.message || "Finish the required items below."}
            </p>
          ) : null}
        </div>
      </div>

      {guidedIssue ? (
        <div className="qms-audit-setup-stage__required-guide" id="audit-occurrence-setup-required" role="alert">
          <AlertTriangle size={17} aria-hidden />
          <div>
            <strong>Setup must be completed before advancing</strong>
            <p>{guidedIssue.message} The required control is highlighted below; the page will not reposition after you begin interacting with it.</p>
          </div>
          <button type="button" onClick={() => showRequiredField(guidedIssue.field, guidedIssue.tile)}>Show required field</button>
        </div>
      ) : null}

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
              {definitionDirty ? "Unsaved" : readiness.definitionReady ? "Saved" : "Required"}
            </span>
          </summary>
          <div className="qms-audit-setup-tile__body">
            <label id="audit-setup-field-title" className={guidedClass("title")}>
              <span>Title</span>
              <input disabled={!canManage} value={draft.title} onChange={(event) => { clearGuidance("title"); setDraft({ ...draft, title: event.target.value }); }} />
            </label>
            <div className="qms-audit-setup-stage__fields">
              <label id="audit-setup-field-scope" className={guidedClass("scope")}>
                <span>Scope</span>
                <textarea
                  disabled={!canManage}
                  rows={2}
                  value={draft.scope}
                  onChange={(event) => { clearGuidance("scope"); setDraft({ ...draft, scope: event.target.value }); }}
                />
              </label>
              <label id="audit-setup-field-criteria" className={guidedClass("criteria")}>
                <span>Criteria</span>
                <textarea
                  disabled={!canManage}
                  rows={2}
                  value={draft.criteria}
                  onChange={(event) => { clearGuidance("criteria"); setDraft({ ...draft, criteria: event.target.value }); }}
                />
              </label>
            </div>
            <div className="qms-audit-setup-stage__fields">
              <label id="audit-setup-field-auditee" className={guidedClass("auditee")}>
                <span>Auditee representative</span>
                <input
                  disabled={!canManage}
                  value={draft.auditee}
                  onChange={(event) => { clearGuidance("auditee"); setDraft({ ...draft, auditee: event.target.value }); }}
                />
                <small className="qms-audit-setup-field-help">Coordination contact for the department or process being audited.</small>
              </label>
              <label>
                <span>Auditee email</span>
                <input
                  type="email"
                  disabled={!canManage}
                  value={draft.auditeeEmail}
                  onChange={(event) => { clearGuidance("auditee"); setDraft({ ...draft, auditeeEmail: event.target.value }); }}
                />
              </label>
              <label id="audit-setup-field-plannedStart" className={guidedClass("plannedStart")}>
                <span>Planned start date</span>
                <input
                  type="date"
                  disabled={!canManage}
                  value={draft.plannedStart}
                  onBlur={correctDefinitionDates}
                  onChange={(event) => { clearGuidance("plannedStart"); setDraft({ ...draft, plannedStart: event.target.value }); }}
                />
              </label>
              <label id="audit-setup-field-plannedStartTime" className={guidedClass("plannedStartTime")}>
                <span>Planned start time</span>
                <input
                  type="time"
                  min="09:00"
                  max="17:00"
                  step={900}
                  disabled={!canManage}
                  value={draft.plannedStartTime}
                  onBlur={correctDefinitionDates}
                  onChange={(event) => { clearGuidance("plannedStartTime"); setDraft({ ...draft, plannedStartTime: event.target.value }); }}
                />
              </label>
              <label id="audit-setup-field-plannedEnd" className={guidedClass("plannedEnd")}>
                <span>Planned end date</span>
                <input
                  type="date"
                  disabled={!canManage}
                  min={draft.plannedStart || undefined}
                  value={draft.plannedEnd}
                  onBlur={correctDefinitionDates}
                  onChange={(event) => { clearGuidance("plannedEnd"); setDraft({ ...draft, plannedEnd: event.target.value }); }}
                />
              </label>
              <label id="audit-setup-field-plannedEndTime" className={guidedClass("plannedEndTime")}>
                <span>Planned end time</span>
                <input
                  type="time"
                  min={draft.plannedStartTime || "09:00"}
                  max="17:00"
                  step={900}
                  disabled={!canManage}
                  value={draft.plannedEndTime}
                  onBlur={correctDefinitionDates}
                  onChange={(event) => { clearGuidance("plannedEndTime"); setDraft({ ...draft, plannedEndTime: event.target.value }); }}
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
                  onBlur={() => setDraft({ ...draft, reminderIntervalDays: String(Math.max(1, Math.min(60, Number(draft.reminderIntervalDays) || 7))) })}
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

        <details
          className={`qms-audit-setup-tile${guidedField === "leadAuditorUserId" ? " is-guided-required" : ""}`}
          id="audit-occurrence-team-wrap"
          open={openTile === "team"}
          onPointerDownCapture={() => clearGuidance("leadAuditorUserId")}
          onKeyDownCapture={() => clearGuidance("leadAuditorUserId")}
        >
          <summary onClick={selectTile("team")}>
            <span className="qms-audit-setup-tile__step" aria-hidden>2</span>
            <span className="qms-audit-setup-tile__title">Audit team</span>
            <span className={`qms-audit-setup-tile__hint${readiness.leadAssigned && (savedTeam.ready || savedTeam.pending) ? "" : " is-warning"}`}>
              {teamDirty
                ? "Unsaved changes"
                : savedTeam.message ||
                  (readiness.leadAssigned ? "Lead assigned" : "Assign lead")}
            </span>
            <span className={`qms-audit-setup-tile__state${savedTeam.ready && !teamDirty ? " is-complete" : " is-required"}`}>
              {teamDirty
                ? "Unsaved"
                : savedTeam.ready
                  ? "Verified"
                  : savedTeam.pending
                    ? "Checking"
                    : readiness.leadAssigned
                      ? "Needs review"
                      : "Required"}
            </span>
          </summary>
          <div className="qms-audit-setup-tile__body" id="audit-setup-field-leadAuditorUserId">
            <AuditAssignmentGovernancePanel key={auditId} amoCode={amoCode} auditKey={auditKey} onDirtyChange={setTeamDirty} />
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
              <div className="qms-audit-setup-stage__meetings-wrap">
                {canManage ? (
                  <div className="qms-audit-setup-stage__quick-schedule">
                    <div>
                      <strong>Schedule both fast</strong>
                      <p>Uses audit dates. For Teams, open the meeting and paste the join links below.</p>
                    </div>
                    <div className="qms-audit-setup-stage__quick-schedule-actions">
                      {MODALITY_OPTIONS.map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          disabled={definitionDirty || meetingMutation.isPending || !draft.plannedStart || !draft.plannedEnd}
                          title={option.hint}
                          onClick={() => void scheduleMeetingPair(option.value)}
                        >
                          {option.value === "ONLINE" ? <Video size={14} /> : null}
                          {option.label}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="qms-audit-setup-stage__meetings">
                  {renderMeeting("OPENING", openingMeeting, openingDraft, setOpeningDraft)}
                  {renderMeeting("CLOSING", closingMeeting, closingDraft, setClosingDraft)}
                </div>
              </div>
            ) : null}
          </div>
        </details>

        <details className="qms-audit-setup-tile" id="audit-occurrence-notice" open={openTile === "notice"}>
          <summary onClick={selectTile("notice")}>
            <span className="qms-audit-setup-tile__step" aria-hidden>4</span>
            <span className="qms-audit-setup-tile__title">Audit notice</span>
            <span className="qms-audit-setup-tile__hint">
              {latestNotice ? latestNotice.status.replaceAll("_", " ") : "Not created"}
            </span>
            <span className="qms-audit-setup-tile__state">Governance</span>
          </summary>
          <div className="qms-audit-setup-tile__body">
            {noticesQuery.isError || policiesQuery.isError || templateQuery.isError ? (
              <div className="qms-audit-setup-stage__section-error" role="alert">
                <span>
                  {errorMessage(noticesQuery.error || policiesQuery.error || templateQuery.error, "Audit notice controls could not be loaded.")}
                </span>
                <button
                  type="button"
                  onClick={() => void Promise.all([noticesQuery.refetch(), policiesQuery.refetch(), templateQuery.refetch()])}
                >
                  <RefreshCw size={14} /> Retry notice
                </button>
              </div>
            ) : null}
            {noticesQuery.isPending || policiesQuery.isPending || templateQuery.isPending ? (
              <p className="qms-audit-setup-stage__empty">Loading notice controls…</p>
            ) : null}
            {!templateQuery.isPending && !templateQuery.isError ? (
              <div className="qms-audit-notice-template">
                <label>
                  <span>Template catalogue · for new notices</span>
                  <select
                    value={selectedTemplateId}
                    disabled={!canManageNotice || Boolean(latestNotice) || templateMutation.isPending}
                    onChange={(event) => event.target.value && templateMutation.mutate(event.target.value)}
                  >
                    {!selectedTemplateId ? <option value="">No form selected</option> : null}
                    {templateQuery.data?.items.map((item) => (
                      <option key={item.document_id} value={item.document_id}>
                        {item.code} · {item.title}{item.current_revision ? ` · current Rev ${item.current_revision}` : " · revision pending"}
                      </option>
                    ))}
                  </select>
                </label>
                <small>
                  {selectedTemplate
                    ? selectedTemplate.ready
                      ? `Current published revision ${selectedTemplate.current_revision}${selectedTemplate.effective_date ? ` effective ${selectedTemplate.effective_date}` : ""}.`
                      : "The DMS record exists; publish its first revision to replace the built-in form layout."
                    : "Add an active Form or Template in the tenant DMS to make it available here."}
                  {latestNotice ? " This notice keeps the form revision captured when its draft was created." : " Historical revisions cannot be selected."}
                </small>
              </div>
            ) : null}
            {!noticesQuery.isError && !policiesQuery.isError && !noticesQuery.isPending && !policiesQuery.isPending && latestNotice ? (
              <dl className="qms-audit-setup-stage__notice-meta">
                <div>
                  <dt>Status</dt>
                  <dd>{latestNotice.status.replaceAll("_", " ")}</dd>
                </div>
                <div>
                  <dt>Notice revision</dt>
                  <dd>{latestNotice.revision_no}</dd>
                </div>
                <div>
                  <dt>Minimum lead time to audit start</dt>
                  <dd>{latestNotice.required_notice_days} days</dd>
                </div>
                <div>
                  <dt>Notice date</dt>
                  <dd>{setupDateLabel(latestNotice.notice_date)}</dd>
                </div>
                <div>
                  <dt>Template captured for this notice</dt>
                  <dd>{latestNotice.form_number}{latestNotice.form_revision ? ` · Rev ${latestNotice.form_revision}` : ""}</dd>
                </div>
                <div>
                  <dt>Signed by</dt>
                  <dd>{latestNotice.artifact?.signed_by_name || "Not recorded"}</dd>
                </div>
                <div>
                  <dt>Approved</dt>
                  <dd>{latestNotice.approved_at ? setupDateLabel(latestNotice.approved_at) : "Not recorded"}</dd>
                </div>
                <div>
                  <dt>Delivered</dt>
                  <dd>{latestNotice.delivered_at ? setupDateLabel(latestNotice.delivered_at) : "Not delivered"}</dd>
                </div>
              </dl>
            ) : !noticesQuery.isError && !policiesQuery.isError && !noticesQuery.isPending && !policiesQuery.isPending ? (
              <p className="qms-audit-setup-stage__empty">No notice yet.</p>
            ) : null}
            {!noticesQuery.isError && !policiesQuery.isError && !noticesQuery.isPending && !policiesQuery.isPending ? (
              <>
                {noticePeriodShort ? (
                  <div className="qms-audit-setup-stage__supporting-warning" role="status">
                    <AlertTriangle size={15} aria-hidden />
                    <div>
                      <strong>Notice period is short of the configured {requiredNoticeDays}-day lead time.</strong>
                      <p>
                        This is not a hard block. Enter a short-notice waiver reason to continue
                        generating or submitting the notice.
                      </p>
                      <label className="qms-audit-setup-stage__waiver">
                        <span>Short-notice waiver reason</span>
                        <textarea
                          rows={2}
                          value={shortNoticeWaiverReason}
                          onChange={(event) => setShortNoticeWaiverReason(event.target.value)}
                          placeholder="Why this notice is issued inside the configured lead time"
                          disabled={!canManageNotice}
                        />
                      </label>
                    </div>
                  </div>
                ) : null}
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
                        disabled={
                          createNoticeMutation.isPending ||
                          noticeReason.trim().length < 8 ||
                          !shortNoticeWaiverReady
                        }
                        onClick={() => createNoticeMutation.mutate()}
                      >
                        <CalendarClock size={15} /> Create notice draft
                      </button>
                    ) : null}
                    {latestNotice ? (
                      <button
                        type="button"
                        className="is-primary"
                        disabled={
                          previewNoticeMutation.isPending ||
                          noticeReason.trim().length < 8 ||
                          !shortNoticeWaiverReady
                        }
                        onClick={() => previewNoticeMutation.mutate(latestNotice)}
                      >
                        <Eye size={15} /> {latestNotice.artifact ? "View final notice" : "Generate final preview"}
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
                    Generate and inspect the final signed document before sending. The stored PDF shown in the preview, including its QR record link and hash, is the exact file attached to the email.
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
              <AuditNoticePdfPreview
                url={noticePreview.url}
                title={`Final audit notice revision ${previewedNotice.revision_no}`}
              />
            </div>
            <footer>
              <div className="qms-audit-notice-modal__record">
                <strong>
                  {previewedNotice.artifact?.source_type === "UPLOADED"
                    ? "Attached signed notice"
                    : "Generated and electronically signed notice"}
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
                <button type="button" onClick={() => downloadBlob(noticePreview.blob, noticePreview.filename)}>
                  <Download size={15} /> Download PDF
                </button>
                {canManageNotice && ["DRAFT", "UNDER_REVIEW", "APPROVED", "GENERATED"].includes(previewedNotice.status) ? (
                  <button
                    type="button"
                    className="is-primary"
                    disabled={
                      submitNoticeMutation.isPending ||
                      noticeReason.trim().length < 8 ||
                      !shortNoticeWaiverReady
                    }
                    onClick={() => submitNoticeMutation.mutate(previewedNotice)}
                  >
                    <Send size={15} /> Send notice and email
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
