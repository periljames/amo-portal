import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CalendarCheck2, CheckCircle2, ShieldAlert } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { hasQmsRolePermission } from "../../app/routeGuards";
import { ApiClientError } from "../../services/apiClient";
import {
  getAuditProgramme,
  getPlannerScheduleOptions,
  scheduleAuditProgrammeItem,
  type AuditScheduleFrequency,
  type PlannerConflict,
  type ProgrammeScheduleCreate,
} from "../../services/qmsAuditProgramme";
import "../../styles/qms-audit-programme.css";
import "../../styles/qms-audit-programme-workflow.css";

const FREQUENCY_BY_RECURRENCE: Record<string, AuditScheduleFrequency | undefined> = {
  ONE_TIME: "ONE_TIME",
  MONTHLY: "MONTHLY",
  QUARTERLY: "QUARTERLY",
  SEMI_ANNUAL: "BI_ANNUAL",
  ANNUAL: "ANNUAL",
};

function criteriaText(criteria: Array<string | Record<string, unknown>>): string {
  return criteria.map((entry) => (typeof entry === "string" ? entry : JSON.stringify(entry))).join("\n");
}

function conflictDetail(error: unknown): PlannerConflict[] {
  if (!(error instanceof ApiClientError) || error.status !== 409 || !error.body || typeof error.body !== "object") {
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
  duration_days: string;
  kind: string;
  audit_scope_id: string;
  location: string;
  scope: string;
  criteria: string;
  notes: string;
  auditee: string;
  lead_auditor_user_id: string;
  observer_auditor_user_id: string;
  assistant_auditor_user_id: string;
  notify_auditors: boolean;
  notify_auditees: boolean;
};

export type QmsAuditProgrammeSchedulePanelProps = {
  amoCode: string;
  programmeId: string;
  itemId: string;
  variant?: "page" | "embedded";
  onCancel?: () => void;
  onScheduled?: (scheduleId: string) => void;
};

const QmsAuditProgrammeSchedulePanel: React.FC<QmsAuditProgrammeSchedulePanelProps> = ({
  amoCode,
  programmeId,
  itemId,
  variant = "page",
  onCancel,
  onScheduled,
}) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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
  const expectedFrequency = item ? FREQUENCY_BY_RECURRENCE[item.recurrence] : undefined;

  const formDefaults = useMemo<ScheduleFormState>(
    () => ({
      title: item?.title || "",
      next_due_date: item?.target_start || programme?.period_start || "",
      start_time: "09:00",
      end_time: "10:00",
      duration_days: "1",
      kind: "INTERNAL",
      audit_scope_id: "",
      location: "",
      scope: item?.scope || "",
      criteria: item ? criteriaText(item.criteria) : "",
      notes: "",
      auditee: item?.auditable_entity?.display_label || "",
      lead_auditor_user_id: "",
      observer_auditor_user_id: "",
      assistant_auditor_user_id: "",
      notify_auditors: true,
      notify_auditees: true,
    }),
    [item, programme?.period_start],
  );
  const [formByItem, setFormByItem] = useState<Record<string, ScheduleFormState>>({});
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

  const scheduleMutation = useMutation({
    mutationFn: (allowConflicts: boolean) => {
      if (!programme || !item || !expectedFrequency) {
        throw new Error("This programme requirement cannot be scheduled with the current planner cadence.");
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
        duration_days: Math.max(1, Number(form.duration_days) || 1),
        timezone_name: optionsQuery.data?.timezone_name || "Africa/Nairobi",
        location: form.location.trim() || undefined,
        scope: form.scope.trim(),
        criteria: form.criteria.trim() || undefined,
        notes: form.notes.trim() || undefined,
        auditee: form.auditee.trim() || undefined,
        lead_auditor_user_id: form.lead_auditor_user_id || undefined,
        observer_auditor_user_id: form.observer_auditor_user_id || undefined,
        assistant_auditor_user_id: form.assistant_auditor_user_id || undefined,
        notify_auditors: form.notify_auditors,
        notify_auditees: form.notify_auditees,
        notify_attendees: true,
        reminder_interval_days: 7,
        automation_active: true,
        allow_conflicts: allowConflicts,
        conflict_override_reason: allowConflicts ? overrideReason.trim() : undefined,
      };
      return scheduleAuditProgrammeItem(amoCode, programme.id, item.id, payload);
    },
    onSuccess: async (schedule) => {
      setConflicts([]);
      setResultScheduleId(schedule.id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["qms-audit-programme", amoCode, programmeId] }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-programmes", amoCode] }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-programme-scheduling-queue", amoCode] }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-programme-schedule-links", amoCode, programmeId] }),
        queryClient.invalidateQueries({ queryKey: ["qms-planner"] }),
      ]);
      onScheduled?.(schedule.id);
    },
    onError: (error) => setConflicts(conflictDetail(error)),
  });

  const programmeHref = `/maintenance/${encodeURIComponent(amoCode)}/quality/audits/program`;
  const calendarHref = `/maintenance/${encodeURIComponent(amoCode)}/quality/calendar/week`;
  const people = optionsQuery.data?.people || [];
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
      <header className={`qms-audit-programme__header${embedded ? " qms-audit-programme__header--embedded" : ""}`}>
        <div>
          {!embedded ? (
            <span>
              <CalendarCheck2 size={15} /> Audit Programme → Quality Planner
            </span>
          ) : null}
          <h2>Schedule programme requirement</h2>
          {!embedded ? (
            <p>
              Create the authoritative planner schedule. The programme requirement changes to Scheduled only if this
              transaction succeeds.
            </p>
          ) : (
            <p>Creates the authoritative Planner V2 schedule for this programme requirement.</p>
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
          <AlertTriangle size={16} /> {loadError instanceof Error ? loadError.message : "Scheduling data could not be loaded."}
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
                {item.auditable_entity?.display_label || "Auditable entity unavailable"} ·{" "}
                {item.recurrence.replaceAll("_", " ")}
              </p>
            </div>
            <span className={`is-${programme.status.toLowerCase()}`}>{programme.status.replaceAll("_", " ")}</span>
          </header>

          <div className="qms-audit-programme-flow__schedule-context" aria-label="Scheduling context">
            <article>
              <span>Source programme</span>
              <strong title={programme.title}>{programme.title}</strong>
              <small title={`${programme.programme_ref} · ${programme.status.replaceAll("_", " ")}`}>{programme.programme_ref} · {programme.status.replaceAll("_", " ")}</small>
            </article>
            <article>
              <span>Requirement</span>
              <strong title={item.title}>{item.title}</strong>
              <small>{item.audit_type.replaceAll("_", " ")} · {item.state.replaceAll("_", " ")}</small>
            </article>
            <article>
              <span>Universe / target</span>
              <strong title={item.auditable_entity?.display_label || "Unlinked entity"}>{item.auditable_entity?.display_label || "Unlinked entity"}</strong>
              <small>{item.auditable_entity?.entity_type?.replaceAll("_", " ") || "No entity type"}</small>
            </article>
            <article>
              <span>Scheduling window</span>
              <strong>
                {(item.target_start || programme.period_start || "—").slice(0, 10)} → {(item.target_end || programme.period_end || "—").slice(0, 10)}
              </strong>
              <small>Proposed date · {form.next_due_date || "not set"}</small>
            </article>
            <article>
              <span>Team / auditor</span>
              <strong>
                {people.find((person) => person.id === form.lead_auditor_user_id)?.full_name || "Lead unassigned"}
              </strong>
              <small>
                {[form.observer_auditor_user_id, form.assistant_auditor_user_id].filter(Boolean).length
                  ? `${[form.observer_auditor_user_id, form.assistant_auditor_user_id].filter(Boolean).length} additional auditor(s)`
                  : "Observer / assistant optional"}
              </small>
            </article>
            <article>
              <span>Resulting schedule state</span>
              <strong>{resultScheduleId ? "SCHEDULED" : item.state.replaceAll("_", " ")}</strong>
              <small>{expectedFrequency ? `Cadence ${expectedFrequency.replaceAll("_", " ")}` : "Cadence unsupported"}</small>
            </article>
          </div>

          {!canSchedule ? (
            <div className="qms-audit-programme__error" role="alert">
              <ShieldAlert size={16} />
              {!canManage
                ? "Scheduling requires audit manage permission. You can review this requirement, but creating a planner schedule is unavailable."
                : !expectedFrequency
                  ? `Recurrence ${item.recurrence} has no deterministic recurring cadence in the authoritative planner. Amend the programme requirement before scheduling.`
                  : item.state !== "PLANNED"
                    ? `This requirement is already ${item.state.toLowerCase().replaceAll("_", " ")} and cannot create another schedule.`
                    : `Programme revision ${programme.status} must be approved before requirements can be scheduled.`}
            </div>
          ) : null}

          {resultScheduleId ? (
            <div className="qms-audit-programme-flow__schedule-success" role="status">
              <div>
                <strong>
                  <CheckCircle2 size={15} /> Schedule created · requirement now Scheduled
                </strong>
                <p>
                  Planner schedule{" "}
                  <code>{resultScheduleId.length > 18 ? `${resultScheduleId.slice(0, 12)}…` : resultScheduleId}</code> is
                  linked to this programme requirement. Continue in Planner V2 — no duplicate calendar here.
                </p>
              </div>
              <div className="qms-audit-programme__actions">
                <button type="button" className="is-primary" onClick={openPlanner}>
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
                scheduleMutation.mutate(false);
              }}
            >
              <header>
                <strong>Authoritative schedule</strong>
                <small>Personnel and location conflicts are checked before the schedule and programme lineage are committed.</small>
              </header>
              <label className="is-wide" htmlFor="programme-schedule-title">
                <span>Schedule title</span>
                <input
                  id="programme-schedule-title"
                  required
                  minLength={3}
                  value={form.title}
                  onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                />
              </label>
              <label htmlFor="programme-schedule-date">
                <span>Date</span>
                <input
                  id="programme-schedule-date"
                  required
                  type="date"
                  min={item.target_start || programme.period_start}
                  max={item.target_end || programme.period_end}
                  value={form.next_due_date}
                  onChange={(event) => setForm((current) => ({ ...current, next_due_date: event.target.value }))}
                />
              </label>
              <label htmlFor="programme-schedule-frequency">
                <span>Frequency</span>
                <input id="programme-schedule-frequency" readOnly value={expectedFrequency || "Unsupported"} />
              </label>
              <label htmlFor="programme-schedule-start">
                <span>Start time</span>
                <input
                  id="programme-schedule-start"
                  required
                  type="time"
                  value={form.start_time}
                  onChange={(event) => setForm((current) => ({ ...current, start_time: event.target.value }))}
                />
              </label>
              <label htmlFor="programme-schedule-end">
                <span>End time</span>
                <input
                  id="programme-schedule-end"
                  type="time"
                  value={form.end_time}
                  onChange={(event) => setForm((current) => ({ ...current, end_time: event.target.value }))}
                />
              </label>
              <label htmlFor="programme-schedule-duration">
                <span>Duration · days</span>
                <input
                  id="programme-schedule-duration"
                  type="number"
                  min={1}
                  max={90}
                  value={form.duration_days}
                  onChange={(event) => setForm((current) => ({ ...current, duration_days: event.target.value }))}
                />
              </label>
              <label htmlFor="programme-schedule-kind">
                <span>Audit kind</span>
                <select
                  id="programme-schedule-kind"
                  value={form.kind}
                  onChange={(event) => setForm((current) => ({ ...current, kind: event.target.value }))}
                >
                  {(optionsQuery.data?.kinds || ["INTERNAL", "EXTERNAL", "THIRD_PARTY"]).map((kind) => (
                    <option key={kind} value={kind}>
                      {kind.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor="programme-schedule-scope-id">
                <span>Audit scope</span>
                <select
                  id="programme-schedule-scope-id"
                  value={form.audit_scope_id}
                  onChange={(event) => setForm((current) => ({ ...current, audit_scope_id: event.target.value }))}
                >
                  <option value="">Use planner default for kind</option>
                  {(optionsQuery.data?.scopes || []).map((scope) => (
                    <option key={scope.id} value={scope.id}>
                      {scope.code} · {scope.name}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor="programme-schedule-location">
                <span>Location</span>
                <input
                  id="programme-schedule-location"
                  value={form.location}
                  onChange={(event) => setForm((current) => ({ ...current, location: event.target.value }))}
                />
              </label>
              <label className="is-wide" htmlFor="programme-schedule-scope">
                <span>Scope</span>
                <textarea
                  id="programme-schedule-scope"
                  required
                  minLength={3}
                  rows={3}
                  value={form.scope}
                  onChange={(event) => setForm((current) => ({ ...current, scope: event.target.value }))}
                />
              </label>
              <label className="is-wide" htmlFor="programme-schedule-criteria">
                <span>Criteria</span>
                <textarea
                  id="programme-schedule-criteria"
                  rows={3}
                  value={form.criteria}
                  onChange={(event) => setForm((current) => ({ ...current, criteria: event.target.value }))}
                />
              </label>
              <label htmlFor="programme-schedule-auditee">
                <span>Auditee / unit</span>
                <input
                  id="programme-schedule-auditee"
                  value={form.auditee}
                  onChange={(event) => setForm((current) => ({ ...current, auditee: event.target.value }))}
                />
              </label>
              <label htmlFor="programme-schedule-lead">
                <span>Lead auditor</span>
                <select
                  id="programme-schedule-lead"
                  value={form.lead_auditor_user_id}
                  onChange={(event) => setForm((current) => ({ ...current, lead_auditor_user_id: event.target.value }))}
                >
                  <option value="">Unassigned</option>
                  {people.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.full_name}
                      {person.department_name ? ` · ${person.department_name}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor="programme-schedule-observer">
                <span>Observer auditor</span>
                <select
                  id="programme-schedule-observer"
                  value={form.observer_auditor_user_id}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, observer_auditor_user_id: event.target.value }))
                  }
                >
                  <option value="">None</option>
                  {people.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.full_name}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor="programme-schedule-assistant">
                <span>Assistant auditor</span>
                <select
                  id="programme-schedule-assistant"
                  value={form.assistant_auditor_user_id}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, assistant_auditor_user_id: event.target.value }))
                  }
                >
                  <option value="">None</option>
                  {people.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.full_name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="is-wide" htmlFor="programme-schedule-notes">
                <span>Planner notes</span>
                <textarea
                  id="programme-schedule-notes"
                  rows={2}
                  value={form.notes}
                  onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
                />
              </label>
              <label className="is-checkbox" htmlFor="programme-schedule-notify-auditors">
                <input
                  id="programme-schedule-notify-auditors"
                  type="checkbox"
                  checked={form.notify_auditors}
                  onChange={(event) => setForm((current) => ({ ...current, notify_auditors: event.target.checked }))}
                />
                <span>Notify auditors</span>
              </label>
              <label className="is-checkbox" htmlFor="programme-schedule-notify-auditee">
                <input
                  id="programme-schedule-notify-auditee"
                  type="checkbox"
                  checked={form.notify_auditees}
                  onChange={(event) => setForm((current) => ({ ...current, notify_auditees: event.target.checked }))}
                />
                <span>Notify auditee</span>
              </label>
              <footer>
                <button type="button" onClick={cancelAction}>
                  Cancel
                </button>
                <button className="is-primary" disabled={scheduleMutation.isPending || optionsQuery.isLoading}>
                  {scheduleMutation.isPending ? "Checking conflicts…" : "Create authoritative schedule"}
                </button>
              </footer>
            </form>
          ) : null}

          {conflicts.length ? (
            <section className="qms-audit-programme__history" aria-label="Planner conflicts">
              <header>
                <strong>Scheduling conflicts</strong>
                <small>
                  The schedule was not created. Review the affected personnel/location commitments before using a governed
                  override.
                </small>
              </header>
              {conflicts.map((conflict) => (
                <article key={`${conflict.subject_type}-${conflict.subject_id}`}>
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
                  scheduleMutation.mutate(true);
                }}
              >
                <label className="is-wide" htmlFor="programme-schedule-conflict-reason">
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
                    disabled={overrideReason.trim().length < 8 || scheduleMutation.isPending}
                  >
                    Create with governed override
                  </button>
                </footer>
              </form>
            </section>
          ) : mutationError && !resultScheduleId ? (
            <div className="qms-audit-programme__error" role="alert">
              <AlertTriangle size={16} />{" "}
              {mutationError instanceof Error ? mutationError.message : "The authoritative schedule could not be created."}
            </div>
          ) : null}
        </section>
      ) : programmeQuery.isLoading ? (
        <div className="qms-audit-programme__detail">
          <p className="is-empty">Loading programme requirement…</p>
        </div>
      ) : null}
    </section>
  );
};

export default QmsAuditProgrammeSchedulePanel;
