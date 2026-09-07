import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarCheck2,
  CheckCircle2,
  ShieldAlert,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { hasQmsRolePermission } from "../../app/routeGuards";
import { useToast } from "../../components/feedback/ToastProvider";
import ScheduleWeekendConfirmDialog from "../../features/qms/ScheduleWeekendConfirmDialog";
import {
  parseWeekendConfirmationDetail,
  type WeekendConfirmationDetail,
  type WeekendPolicy,
} from "../../features/qms/scheduleWeekend";
import { ApiClientError } from "../../services/apiClient";
import {
  getAuditProgramme,
  getPlannerScheduleOptions,
  scheduleAuditProgrammeItem,
  type AuditScheduleFrequency,
  type PlannerConflict,
  type ProgrammeScheduleCreate,
} from "../../services/qmsAuditProgramme";
import {
  ProgrammeLocationSelect,
  ProgrammeObserverSelect,
  SupportingAuditorPicker,
} from "./QmsAuditPlanningFields";
import {
  suggestedLocationCode,
  withoutLeadAuditor,
  workingDayCount,
} from "./qmsAuditProgrammePlanning";
import "../../styles/qms-audit-programme.css";
import "../../styles/qms-audit-programme-workflow.css";

const FREQUENCY_BY_RECURRENCE: Record<
  string,
  AuditScheduleFrequency | undefined
> = {
  ONE_TIME: "ONE_TIME",
  MONTHLY: "MONTHLY",
  QUARTERLY: "QUARTERLY",
  SEMI_ANNUAL: "BI_ANNUAL",
  ANNUAL: "ANNUAL",
};

function criteriaText(
  criteria: Array<string | Record<string, unknown>>,
): string {
  return criteria
    .map((entry) => (typeof entry === "string" ? entry : JSON.stringify(entry)))
    .join("\n");
}

function conflictDetail(error: unknown): PlannerConflict[] {
  if (
    !(error instanceof ApiClientError) ||
    error.status !== 409 ||
    !error.body ||
    typeof error.body !== "object"
  ) {
    return [];
  }
  const detail = (error.body as { detail?: unknown }).detail;
  if (!detail || typeof detail !== "object") return [];
  const conflicts = (detail as { conflicts?: unknown }).conflicts;
  return Array.isArray(conflicts) ? (conflicts as PlannerConflict[]) : [];
}

type ScheduleFormState = {
  title: string;
  next_due_date: string;
  start_time: string;
  end_time: string;
  kind: string;
  audit_scope_id: string;
  location: string;
  scope: string;
  criteria: string;
  notes: string;
  auditee: string;
  auditee_user_id: string;
  lead_auditor_user_id: string;
  observer_auditor_user_id: string;
  supporting_auditor_user_ids: string[];
  notify_auditors: boolean;
  notify_auditees: boolean;
};

export type QmsAuditProgrammeSchedulePanelProps = {
  amoCode: string;
  programmeId: string;
  itemId: string;
  variant?: "page" | "embedded";
  initialValues?: {
    title?: string;
    next_due_date?: string;
    start_time?: string;
  };
  onCancel?: () => void;
  onScheduled?: (scheduleId: string) => void;
};

const QmsAuditProgrammeSchedulePanel: React.FC<
  QmsAuditProgrammeSchedulePanelProps
> = ({
  amoCode,
  programmeId,
  itemId,
  variant = "page",
  initialValues,
  onCancel,
  onScheduled,
}) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const embedded = variant === "embedded";
  const canManage = hasQmsRolePermission("qms.audit.manage");

  const programmeQuery = useQuery({
    queryKey: ["qms-audit-programme", amoCode, programmeId],
    queryFn: ({ signal }) => getAuditProgramme(amoCode, programmeId, signal),
    enabled: Boolean(programmeId && itemId),
    staleTime: 3_000,
  });
  const optionsQuery = useQuery({
    queryKey: ["qms-planner-schedule-options", amoCode],
    queryFn: ({ signal }) => getPlannerScheduleOptions(amoCode, signal),
    enabled: Boolean(programmeId && itemId && canManage),
    staleTime: 10_000,
  });
  const programme = programmeQuery.data;
  const item = programme?.items?.find((entry) => entry.id === itemId);
  const expectedFrequency = item
    ? FREQUENCY_BY_RECURRENCE[item.recurrence]
    : undefined;

  const formDefaults = useMemo<ScheduleFormState>(
    () => ({
      title: initialValues?.title ?? item?.title ?? "",
      next_due_date:
        initialValues?.next_due_date ??
        item?.target_start ??
        programme?.period_start ??
        "",
      start_time:
        initialValues?.start_time ??
        String(item?.default_start_time || "09:00").slice(0, 5),
      end_time: String(item?.default_end_time || "17:00").slice(0, 5),
      kind: programme?.programme_kind || "INTERNAL",
      audit_scope_id: "",
      location:
        item?.default_location ||
        suggestedLocationCode(
          item?.auditable_entity,
          optionsQuery.data?.locations || [],
        ),
      scope: item?.scope || "",
      criteria: item ? criteriaText(item.criteria) : "",
      notes: "",
      auditee: item?.auditable_entity?.display_label || "",
      auditee_user_id: item?.auditee_user_id || "",
      lead_auditor_user_id: item?.lead_auditor_user_id || "",
      observer_auditor_user_id: item?.observer_auditor_user_id || "",
      supporting_auditor_user_ids: withoutLeadAuditor(
        item?.supporting_auditor_user_ids || [],
        item?.lead_auditor_user_id,
        item?.observer_auditor_user_id,
      ),
      notify_auditors: item?.notify_auditors !== false,
      notify_auditees: item?.notify_auditees !== false,
    }),
    [
      initialValues,
      item,
      optionsQuery.data?.locations,
      programme?.period_start,
      programme?.programme_kind,
    ],
  );
  const [formByItem, setFormByItem] = useState<
    Record<string, ScheduleFormState>
  >({});
  const form = formByItem[itemId] || formDefaults;
  const setForm = (updater: React.SetStateAction<ScheduleFormState>) => {
    setFormByItem((currentByItem) => {
      const current = currentByItem[itemId] || formDefaults;
      const next = typeof updater === "function" ? updater(current) : updater;
      return { ...currentByItem, [itemId]: next };
    });
  };
  const [conflicts, setConflicts] = useState<PlannerConflict[]>([]);
  const [overrideReason, setOverrideReason] = useState("");
  const [resultScheduleId, setResultScheduleId] = useState("");
  const [weekendPrompt, setWeekendPrompt] =
    useState<WeekendConfirmationDetail | null>(null);
  const [pendingAllowConflicts, setPendingAllowConflicts] = useState(false);
  const [weekendPolicy, setWeekendPolicy] = useState<WeekendPolicy | null>(
    null,
  );

  const scheduleMutation = useMutation({
    mutationFn: ({
      allowConflicts,
      weekendPolicy: policy,
    }: {
      allowConflicts: boolean;
      weekendPolicy?: WeekendPolicy | null;
    }) => {
      if (!programme || !item || !expectedFrequency) {
        throw new Error(
          "This programme requirement cannot be scheduled with its current frequency.",
        );
      }
      const payload: ProgrammeScheduleCreate = {
        title: form.title.trim(),
        domain: "AMO",
        kind: form.kind,
        audit_scope_id: form.audit_scope_id || undefined,
        frequency: expectedFrequency,
        next_due_date: form.next_due_date,
        start_time: form.start_time,
        end_time: form.end_time || undefined,
        duration_days:
          item.default_duration_days ||
          workingDayCount(item.target_start, item.target_end),
        timezone_name: optionsQuery.data?.timezone_name || "Africa/Nairobi",
        location: form.location.trim() || undefined,
        scope: form.scope.trim(),
        criteria: form.criteria.trim() || undefined,
        notes: form.notes.trim() || undefined,
        auditee: form.auditee.trim() || undefined,
        auditee_user_id: form.auditee_user_id || undefined,
        lead_auditor_user_id: form.lead_auditor_user_id || undefined,
        observer_auditor_user_id: form.observer_auditor_user_id || undefined,
        assistant_auditor_user_id:
          form.supporting_auditor_user_ids[0] || undefined,
        attendee_user_ids: form.supporting_auditor_user_ids.slice(1),
        notify_auditors: form.notify_auditors,
        notify_auditees: form.notify_auditees,
        notify_attendees: true,
        reminder_interval_days: 7,
        automation_active: true,
        allow_conflicts: allowConflicts,
        conflict_override_reason: allowConflicts
          ? overrideReason.trim()
          : undefined,
        weekend_policy: policy || undefined,
      };
      return scheduleAuditProgrammeItem(
        amoCode,
        programme.id,
        item.id,
        payload,
      );
    },
    onSuccess: async (schedule) => {
      setConflicts([]);
      setWeekendPrompt(null);
      setWeekendPolicy(null);
      setResultScheduleId(schedule.id);
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["qms-audit-programme", amoCode, programmeId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["qms-audit-programmes", amoCode],
        }),
        queryClient.invalidateQueries({
          queryKey: ["qms-audit-programme-scheduling-queue", amoCode],
        }),
        queryClient.invalidateQueries({
          queryKey: [
            "qms-audit-programme-schedule-links",
            amoCode,
            programmeId,
          ],
        }),
        queryClient.invalidateQueries({ queryKey: ["qms-planner"] }),
      ]);
      pushToast({
        title: "Audit scheduled",
        message: "The governed requirement is now linked to the Quality Calendar.",
        variant: "success",
        dedupeKey: `audit-programme-scheduled:${schedule.id}`,
      });
      onScheduled?.(schedule.id);
    },
    onError: (error) => {
      const weekendDetail = parseWeekendConfirmationDetail(error);
      if (weekendDetail) {
        setWeekendPrompt(weekendDetail);
        setConflicts([]);
        pushToast({
          title: "Working-day confirmation required",
          message: "Confirm how the weekend date should be handled before scheduling.",
          variant: "warning",
          dedupeKey: `audit-programme-weekend:${programmeId}:${itemId}`,
        });
        return;
      }
      const detectedConflicts = conflictDetail(error);
      setConflicts(detectedConflicts);
      pushToast({
        title: detectedConflicts.length
          ? "Auditor schedule conflict"
          : "Audit could not be scheduled",
        message: detectedConflicts.length
          ? "Review the overlapping assignments before saving or record a governed override."
          : error instanceof Error
            ? error.message
            : "The scheduling transaction did not finish.",
        variant: detectedConflicts.length ? "warning" : "error",
        dedupeKey: `audit-programme-schedule-error:${programmeId}:${itemId}`,
      });
    },
  });

  const submitSchedule = (
    allowConflicts: boolean,
    policy: WeekendPolicy | null = weekendPolicy,
  ) => {
    setPendingAllowConflicts(allowConflicts);
    scheduleMutation.mutate({ allowConflicts, weekendPolicy: policy });
  };

  const programmeHref = `/maintenance/${encodeURIComponent(amoCode)}/quality/audits/program`;
  const calendarHref = `/maintenance/${encodeURIComponent(amoCode)}/quality/calendar/week`;
  const people = optionsQuery.data?.people || [];
  const locations = optionsQuery.data?.locations || [];
  const auditorOptions = people.filter((person) => (person.auditor_roles || []).length > 0);
  const leadAuditorOptions = auditorOptions.filter((person) =>
    (person.auditor_roles || []).includes("LEAD_AUDITOR"),
  );
  const canSchedule =
    canManage &&
    programme &&
    item &&
    ["APPROVED", "ACTIVE"].includes(programme.status) &&
    item.state === "PLANNED" &&
    Boolean(expectedFrequency);
  const loadError = programmeQuery.error || optionsQuery.error;
  const mutationError = scheduleMutation.error;

  const cancelAction = () => {
    if (onCancel) onCancel();
    else navigate(programmeHref);
  };

  const openPlanner = () => {
    if (onCancel) onCancel();
    navigate(calendarHref);
  };

  return (
    <section
      className={`qms-audit-programme${embedded ? " qms-audit-programme--embedded" : ""}`}
      aria-label="Schedule audit programme requirement"
    >
      <header
        className={`qms-audit-programme__header${embedded ? " qms-audit-programme__header--embedded" : ""}`}
      >
        <div>
          {!embedded ? (
            <span>
              <CalendarCheck2 size={15} /> Audit Programme → Quality Planner
            </span>
          ) : null}
          <h2>Schedule programme requirement</h2>
          {!embedded ? (
            <p>
              Create the authoritative planner schedule. The programme
              requirement changes to Scheduled only if this transaction
              succeeds.
            </p>
          ) : (
            <p>
              Creates the authoritative Planner V2 schedule for this programme
              requirement.
            </p>
          )}
        </div>
        {!embedded ? (
          <div className="qms-audit-programme__header-actions">
            <button type="button" onClick={cancelAction}>
              Back to programme
            </button>
            <Link to={calendarHref}>Open in Planner</Link>
          </div>
        ) : null}
      </header>

      {loadError ? (
        <div className="qms-audit-programme__error" role="alert">
          <AlertTriangle size={16} />{" "}
          {loadError instanceof Error
            ? loadError.message
            : "Scheduling data could not be loaded."}
        </div>
      ) : null}
      {!programmeQuery.isLoading && programme && !item ? (
        <div className="qms-audit-programme__error" role="alert">
          The selected programme requirement no longer exists in this revision.
        </div>
      ) : null}

      {programme && item ? (
        <section className="qms-audit-programme__detail">
          <header className="qms-audit-programme__detail-header">
            <div>
              <span>
                {programme.programme_ref} · Rev {programme.revision_no}
              </span>
              <h3 title={item.title}>{item.title}</h3>
              <p>
                {item.auditable_entity?.display_label ||
                  "Auditable entity unavailable"}{" "}
                · {item.recurrence.replaceAll("_", " ")}
              </p>
            </div>
            <span className={`is-${programme.status.toLowerCase()}`}>
              {programme.status.replaceAll("_", " ")}
            </span>
          </header>

          <div
            className="qms-audit-programme-flow__schedule-context"
            aria-label="Scheduling context"
          >
            <article>
              <span>Source programme</span>
              <strong title={programme.title}>{programme.title}</strong>
              <small
                title={`${programme.programme_ref} · ${programme.status.replaceAll("_", " ")}`}
              >
                {programme.programme_ref} ·{" "}
                {programme.status.replaceAll("_", " ")}
              </small>
            </article>
            <article>
              <span>Requirement</span>
              <strong title={item.title}>{item.title}</strong>
              <small>
                {item.audit_type.replaceAll("_", " ")} ·{" "}
                {item.state.replaceAll("_", " ")}
              </small>
            </article>
            <article>
              <span>Universe / target</span>
              <strong
                title={
                  item.auditable_entity?.display_label || "Unlinked entity"
                }
              >
                {item.auditable_entity?.display_label || "Unlinked entity"}
              </strong>
              <small>
                {item.auditable_entity?.entity_type?.replaceAll("_", " ") ||
                  "No entity type"}
              </small>
            </article>
            <article>
              <span>Scheduling window</span>
              <strong>
                {(item.target_start || programme.period_start || "—").slice(
                  0,
                  10,
                )}{" "}
                →{" "}
                {(item.target_end || programme.period_end || "—").slice(0, 10)}
              </strong>
              <small>Proposed date · {form.next_due_date || "not set"}</small>
            </article>
            <article>
              <span>Team / auditor</span>
              <strong>
                {people.find(
                  (person) => person.id === form.lead_auditor_user_id,
                )?.full_name || "Lead unassigned"}
              </strong>
              <small>
                {form.supporting_auditor_user_ids.length
                  ? `${form.supporting_auditor_user_ids.length} supporting auditor(s)`
                  : "No supporting auditors"}
              </small>
            </article>
            <article>
              <span>Resulting schedule state</span>
              <strong>
                {resultScheduleId
                  ? "SCHEDULED"
                  : item.state.replaceAll("_", " ")}
              </strong>
              <small>
                {expectedFrequency
                  ? `Frequency ${expectedFrequency.replaceAll("_", " ")}`
                  : "Frequency unsupported"}
              </small>
            </article>
          </div>

          {!canSchedule ? (
            <div className="qms-audit-programme__error" role="alert">
              <ShieldAlert size={16} />
              {!canManage
                ? "Scheduling requires audit manage permission. You can review this requirement, but creating a planner schedule is unavailable."
                : !expectedFrequency
                  ? `Frequency ${item.recurrence.replaceAll("_", " ")} cannot be scheduled automatically. Amend the programme requirement before scheduling.`
                  : item.state !== "PLANNED"
                    ? `This requirement is already ${item.state.toLowerCase().replaceAll("_", " ")} and cannot create another schedule.`
                    : `Programme revision ${programme.status} must be approved before requirements can be scheduled.`}
            </div>
          ) : null}

          {resultScheduleId ? (
            <div
              className="qms-audit-programme-flow__schedule-success"
              role="status"
            >
              <div>
                <strong>
                  <CheckCircle2 size={15} /> Schedule created · requirement now
                  Scheduled
                </strong>
                <p>
                  Planner schedule{" "}
                  <code>
                    {resultScheduleId.length > 18
                      ? `${resultScheduleId.slice(0, 12)}…`
                      : resultScheduleId}
                  </code>{" "}
                  is linked to this programme requirement. Continue in Planner
                  V2 — no duplicate calendar here.
                </p>
              </div>
              <div className="qms-audit-programme__actions">
                <button
                  type="button"
                  className="is-primary"
                  onClick={openPlanner}
                >
                  Open in Planner
                </button>
                <button type="button" onClick={cancelAction}>
                  Return to programme
                </button>
              </div>
            </div>
          ) : null}

          {!resultScheduleId && canSchedule ? (
            <form
              className="qms-audit-programme__form"
              onSubmit={(event) => {
                event.preventDefault();
                setConflicts([]);
                scheduleMutation.reset();
                setWeekendPrompt(null);
                submitSchedule(false);
              }}
            >
              <header>
                <strong>Authoritative schedule</strong>
                <small>
                  Personnel and location conflicts are checked before the
                  schedule and programme lineage are committed.
                </small>
              </header>
              <label className="is-wide" htmlFor="programme-schedule-title">
                <span>Schedule title</span>
                <input
                  id="programme-schedule-title"
                  readOnly
                  value={form.title}
                />
              </label>
              <label htmlFor="programme-schedule-date">
                <span>Date</span>
                <input
                  id="programme-schedule-date"
                  required
                  type="date"
                  min={
                    [
                      item.target_start,
                      programme.period_start,
                      new Date().toISOString().slice(0, 10),
                    ]
                      .filter(Boolean)
                      .sort()
                      .at(-1) ?? undefined
                  }
                  max={item.target_end || programme.period_end}
                  value={form.next_due_date}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      next_due_date: event.target.value,
                    }))
                  }
                />
              </label>
              <label htmlFor="programme-schedule-frequency">
                <span>Frequency</span>
                <input
                  id="programme-schedule-frequency"
                  readOnly
                  value={expectedFrequency || "Unsupported"}
                />
              </label>
              <label htmlFor="programme-schedule-start">
                <span>Start time</span>
                <input
                  id="programme-schedule-start"
                  required
                  type="time"
                  min="09:00"
                  max="17:00"
                  value={form.start_time}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      start_time: event.target.value,
                    }))
                  }
                />
              </label>
              <label htmlFor="programme-schedule-end">
                <span>End time</span>
                <input
                  id="programme-schedule-end"
                  required
                  type="time"
                  min="09:00"
                  max="17:00"
                  value={form.end_time}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      end_time: event.target.value,
                    }))
                  }
                />
              </label>
              <ProgrammeLocationSelect
                id="programme-schedule-location"
                value={form.location}
                locations={locations}
                onChange={(location) =>
                  setForm((current) => ({ ...current, location }))
                }
                required={["FACILITY", "STATION"].includes(
                  item.auditable_entity?.entity_type || "",
                )}
              />
              <label htmlFor="programme-schedule-auditee">
                <span>Auditee representative</span>
                <select
                  id="programme-schedule-auditee"
                  value={form.auditee_user_id}
                  onChange={(event) => {
                    const auditeeUserId = event.target.value;
                    const auditee =
                      people.find((person) => person.id === auditeeUserId)
                        ?.full_name || form.auditee;
                    setForm((current) => ({
                      ...current,
                      auditee_user_id: auditeeUserId,
                      auditee,
                    }));
                  }}
                >
                  <option value="">Use audit area owner</option>
                  {people.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.full_name}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor="programme-schedule-lead">
                <span>Lead auditor</span>
                <select
                  id="programme-schedule-lead"
                  required
                  value={form.lead_auditor_user_id}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      lead_auditor_user_id: event.target.value,
                      observer_auditor_user_id:
                        current.observer_auditor_user_id === event.target.value
                          ? ""
                          : current.observer_auditor_user_id,
                      supporting_auditor_user_ids: withoutLeadAuditor(
                        current.supporting_auditor_user_ids,
                        event.target.value,
                        current.observer_auditor_user_id,
                      ),
                    }))
                  }
                >
                  <option value="">Unassigned</option>
                  {leadAuditorOptions.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.full_name}
                      {person.department_name
                        ? ` · ${person.department_name}`
                        : ""}
                    </option>
                  ))}
                </select>
              </label>
              <ProgrammeObserverSelect
                id="programme-schedule-observer"
                people={auditorOptions}
                leadAuditorUserId={form.lead_auditor_user_id}
                supportingAuditorUserIds={form.supporting_auditor_user_ids}
                value={form.observer_auditor_user_id}
                onChange={(observer_auditor_user_id) =>
                  setForm((current) => ({
                    ...current,
                    observer_auditor_user_id,
                    supporting_auditor_user_ids: withoutLeadAuditor(
                      current.supporting_auditor_user_ids,
                      current.lead_auditor_user_id,
                      observer_auditor_user_id,
                    ),
                  }))
                }
              />
              <SupportingAuditorPicker
                id="programme-schedule-supporting-auditors"
                people={auditorOptions}
                leadAuditorUserId={form.lead_auditor_user_id}
                excludedUserIds={[form.observer_auditor_user_id]}
                value={form.supporting_auditor_user_ids}
                onChange={(supporting_auditor_user_ids) =>
                  setForm((current) => ({
                    ...current,
                    supporting_auditor_user_ids,
                  }))
                }
              />
              <label className="is-wide" htmlFor="programme-schedule-notes">
                <span>Planner notes</span>
                <textarea
                  id="programme-schedule-notes"
                  rows={2}
                  value={form.notes}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      notes: event.target.value,
                    }))
                  }
                />
              </label>
              <label
                className="is-checkbox"
                htmlFor="programme-schedule-notify-auditors"
              >
                <input
                  id="programme-schedule-notify-auditors"
                  type="checkbox"
                  checked={form.notify_auditors}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      notify_auditors: event.target.checked,
                    }))
                  }
                />
                <span>Notify auditors</span>
              </label>
              <label
                className="is-checkbox"
                htmlFor="programme-schedule-notify-auditee"
              >
                <input
                  id="programme-schedule-notify-auditee"
                  type="checkbox"
                  checked={form.notify_auditees}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      notify_auditees: event.target.checked,
                    }))
                  }
                />
                <span>Notify auditee</span>
              </label>
              <footer>
                <button type="button" onClick={cancelAction}>
                  Cancel
                </button>
                <button
                  className="is-primary"
                  disabled={
                    scheduleMutation.isPending ||
                    optionsQuery.isLoading ||
                    !form.lead_auditor_user_id ||
                    form.start_time < "09:00" ||
                    form.end_time > "17:00" ||
                    form.start_time >= form.end_time
                  }
                >
                  {scheduleMutation.isPending
                    ? "Checking conflicts…"
                    : "Create authoritative schedule"}
                </button>
              </footer>
            </form>
          ) : null}

          {conflicts.length ? (
            <section
              className="qms-audit-programme__history"
              aria-label="Planner conflicts"
            >
              <header>
                <strong>Scheduling conflicts</strong>
                <small>
                  The schedule was not created. Review the affected
                  personnel/location commitments before using a governed
                  override.
                </small>
              </header>
              {conflicts.map((conflict) => (
                <article
                  key={`${conflict.subject_type}-${conflict.subject_id}`}
                >
                  <span>
                    <AlertTriangle size={14} />
                    <strong>{conflict.title}</strong>
                  </span>
                  <p>{conflict.reason}</p>
                  <small>
                    {conflict.start_date}
                    {conflict.start_time ? ` · ${conflict.start_time}` : ""}
                    {conflict.location ? ` · ${conflict.location}` : ""}
                  </small>
                </article>
              ))}
              <form
                className="qms-audit-programme__form is-embedded"
                onSubmit={(event) => {
                  event.preventDefault();
                  scheduleMutation.reset();
                  setWeekendPrompt(null);
                  submitSchedule(true);
                }}
              >
                <label
                  className="is-wide"
                  htmlFor="programme-schedule-conflict-reason"
                >
                  <span>Conflict override reason</span>
                  <textarea
                    id="programme-schedule-conflict-reason"
                    required
                    minLength={8}
                    rows={3}
                    value={overrideReason}
                    onChange={(event) => setOverrideReason(event.target.value)}
                    placeholder="Explain why this allocation is operationally acceptable despite the identified conflict."
                  />
                </label>
                <footer>
                  <button
                    type="submit"
                    className="is-primary"
                    disabled={
                      overrideReason.trim().length < 8 ||
                      scheduleMutation.isPending
                    }
                  >
                    Create with governed override
                  </button>
                </footer>
              </form>
            </section>
          ) : mutationError && !resultScheduleId && !weekendPrompt ? (
            <div className="qms-audit-programme__error" role="alert">
              <AlertTriangle size={16} />{" "}
              {mutationError instanceof Error
                ? mutationError.message
                : "The authoritative schedule could not be created."}
            </div>
          ) : null}
        </section>
      ) : programmeQuery.isLoading ? (
        <div className="qms-audit-programme__detail">
          <p className="is-empty">Loading programme requirement…</p>
        </div>
      ) : null}

      {weekendPrompt ? (
        <ScheduleWeekendConfirmDialog
          detail={weekendPrompt}
          busy={scheduleMutation.isPending}
          onCancel={() => {
            setWeekendPrompt(null);
            scheduleMutation.reset();
          }}
          onConfirm={(policy) => {
            setWeekendPolicy(policy);
            setWeekendPrompt(null);
            submitSchedule(pendingAllowConflicts, policy);
          }}
        />
      ) : null}
    </section>
  );
};

export default QmsAuditProgrammeSchedulePanel;
