import React, { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  CalendarPlus,
  CheckCircle2,
  ClipboardCheck,
  Play,
  ShieldCheck,
} from "lucide-react";
import Drawer from "../../components/shared/Drawer";
import { getCachedUser } from "../../services/auth";
import {
  getPlannerScheduleOptions,
  type AuditProgramme,
  type AuditProgrammeItem,
} from "../../services/qmsAuditProgramme";
import {
  qmsCreateAudit,
  qmsListAuditScopes,
  qmsStartAudit,
  type QMSAuditOut,
  type QMSAuditScopeOut,
} from "../../services/qmsCore";
import {
  ProgrammeLocationSelect,
  ProgrammeObserverSelect,
  SupportingAuditorPicker,
} from "../qms/QmsAuditPlanningFields";
import {
  suggestedLocationCode,
  withoutLeadAuditor,
} from "../qms/qmsAuditProgrammePlanning";

export type AuditLaunchMode = "audit" | "surveillance";

type CreatedAuditContext = {
  offerProgramme: boolean;
};

type Props = {
  amoCode: string;
  isOpen: boolean;
  mode: AuditLaunchMode;
  programmes: AuditProgramme[];
  existingAudits: QMSAuditOut[];
  onClose: () => void;
  onCreated: (audit: QMSAuditOut, context: CreatedAuditContext) => void;
  onOpenExisting: (audit: QMSAuditOut) => void;
};

type ProgrammeCandidate = {
  key: string;
  programme: AuditProgramme;
  item: AuditProgrammeItem;
};

const CRITERIA_OPTIONS = [
  "KCARs Part 145 and applicable approved maintenance organisation procedures",
  "Approved manuals, procedures, work instructions and controlled records",
  "ISO 9001-aligned quality controls and applicable statutory requirements",
];

const SURVEILLANCE_FOCUS_OPTIONS = [
  "Hangar maintenance",
  "Line maintenance",
  "Stores and material control",
  "Tooling and calibration",
  "Technical records",
  "Personnel authorisations",
  "Other targeted compliance check",
];

const TIME_OPTIONS = Array.from({ length: 17 }, (_, index) => {
  const minutes = 9 * 60 + index * 30;
  const hours = String(Math.floor(minutes / 60)).padStart(2, "0");
  const remainder = String(minutes % 60).padStart(2, "0");
  return `${hours}:${remainder}`;
});

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function nextWorkingDateIso(): string {
  return moveWeekendToWorkingDay(todayIso());
}

function moveWeekendToWorkingDay(value: string): string {
  const date = new Date(`${value}T00:00:00Z`);
  if (date.getUTCDay() === 6) date.setUTCDate(date.getUTCDate() + 2);
  if (date.getUTCDay() === 0) date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

function durationDays(start: string, end: string): number {
  const left = Date.parse(`${start}T00:00:00Z`);
  const right = Date.parse(`${end}T00:00:00Z`);
  if (!Number.isFinite(left) || !Number.isFinite(right) || right < left)
    return 1;
  return Math.floor((right - left) / 86_400_000) + 1;
}

function endDateForDuration(start: string, days?: number | null): string {
  const date = new Date(`${start}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + Math.max(1, days || 1) - 1);
  return date.toISOString().slice(0, 10);
}

function programmeCriteria(item: AuditProgrammeItem): string {
  return (item.criteria || [])
    .map((entry) => (typeof entry === "string" ? entry : JSON.stringify(entry)))
    .filter(Boolean)
    .join("\n");
}

function preferredScope(
  scopes: QMSAuditScopeOut[],
  kind: string,
): QMSAuditScopeOut | undefined {
  const kindMatches = scopes.filter((scope) => scope.default_kind === kind);
  return (
    kindMatches.find(
      (scope) =>
        scope.code ===
        (kind === "INTERNAL" ? "MO" : kind === "THIRD_PARTY" ? "REG" : "SC"),
    ) ??
    kindMatches[0] ??
    scopes[0]
  );
}

function candidateDate(candidate: ProgrammeCandidate): string {
  const today = todayIso();
  const fixedDates = candidate.item.fixed_dates || [];
  const fixed = fixedDates
    .map((monthDay) => `${candidate.programme.programme_year}-${monthDay}`)
    .filter((value) => value >= today)
    .sort()[0];
  const target =
    candidate.item.target_start && candidate.item.target_start >= today
      ? candidate.item.target_start
      : null;
  return moveWeekendToWorkingDay(fixed || target || nextWorkingDateIso());
}

const AuditLaunchDrawer: React.FC<Props> = ({
  amoCode,
  isOpen,
  mode,
  programmes,
  existingAudits,
  onClose,
  onCreated,
  onOpenExisting,
}) => {
  const currentUser = getCachedUser();
  const candidates = useMemo<ProgrammeCandidate[]>(
    () =>
      programmes
        .filter((programme) =>
          ["APPROVED", "ACTIVE"].includes(programme.status),
        )
        .flatMap((programme) =>
          (programme.items || [])
            .filter((item) => item.state !== "CANCELLED")
            .map((item) => ({
              key: `${programme.id}:${item.id}`,
              programme,
              item,
            })),
        ),
    [programmes],
  );
  const initialCandidate = candidates[0] ?? null;
  const initialDate =
    mode === "surveillance"
      ? todayIso()
      : initialCandidate
        ? candidateDate(initialCandidate)
        : nextWorkingDateIso();
  const [source, setSource] = useState<"programme" | "one-off">(
    mode === "audit" && initialCandidate ? "programme" : "one-off",
  );
  const [programmeKey, setProgrammeKey] = useState(initialCandidate?.key || "");
  const [auditScopeId, setAuditScopeId] = useState("");
  const [title, setTitle] = useState(initialCandidate?.item.title || "");
  const [scopeText, setScopeText] = useState(
    initialCandidate?.item.scope || "",
  );
  const [criteria, setCriteria] = useState(
    initialCandidate
      ? programmeCriteria(initialCandidate.item) || CRITERIA_OPTIONS[0]
      : CRITERIA_OPTIONS[0],
  );
  const [auditeeUserId, setAuditeeUserId] = useState(
    initialCandidate?.item.auditee_user_id || "",
  );
  const [leadAuditorUserId, setLeadAuditorUserId] = useState(
    initialCandidate?.item.lead_auditor_user_id || currentUser?.id || "",
  );
  const [observerAuditorUserId, setObserverAuditorUserId] = useState(
    initialCandidate?.item.observer_auditor_user_id || "",
  );
  const [supportingAuditorUserIds, setSupportingAuditorUserIds] = useState(
    withoutLeadAuditor(
      initialCandidate?.item.supporting_auditor_user_ids || [],
      initialCandidate?.item.lead_auditor_user_id || currentUser?.id,
      initialCandidate?.item.observer_auditor_user_id,
    ),
  );
  const [location, setLocation] = useState(
    initialCandidate?.item.default_location || "",
  );
  const [plannedStart, setPlannedStart] = useState(initialDate);
  const [plannedEnd, setPlannedEnd] = useState(
    endDateForDuration(
      initialDate,
      initialCandidate?.item.default_duration_days,
    ),
  );
  const [startTime, setStartTime] = useState(
    initialCandidate?.item.default_start_time?.slice(0, 5) || "09:00",
  );
  const [endTime, setEndTime] = useState(
    initialCandidate?.item.default_end_time?.slice(0, 5) ||
      (mode === "surveillance" ? "10:00" : "17:00"),
  );
  const [notifyAuditors, setNotifyAuditors] = useState(
    mode === "audit" ? (initialCandidate?.item.notify_auditors ?? true) : false,
  );
  const [notifyAuditees, setNotifyAuditees] = useState(
    mode === "audit" ? (initialCandidate?.item.notify_auditees ?? true) : false,
  );
  const [surveillanceFocus, setSurveillanceFocus] = useState(
    SURVEILLANCE_FOCUS_OPTIONS[0],
  );
  const [customSurveillanceFocus, setCustomSurveillanceFocus] = useState("");
  const [error, setError] = useState<string | null>(null);

  const scopesQuery = useQuery({
    queryKey: ["qms-audit-launch-scopes", amoCode],
    queryFn: () => qmsListAuditScopes({ active: true }),
    staleTime: 5 * 60_000,
    enabled: isOpen,
  });
  const optionsQuery = useQuery({
    queryKey: ["qms-planner-schedule-options", amoCode],
    queryFn: ({ signal }) => getPlannerScheduleOptions(amoCode, signal),
    staleTime: 60_000,
    enabled: isOpen,
  });

  const selectedCandidate =
    candidates.find((candidate) => candidate.key === programmeKey) ?? null;
  const scopes = useMemo(() => scopesQuery.data ?? [], [scopesQuery.data]);
  const people = useMemo(
    () => optionsQuery.data?.people ?? [],
    [optionsQuery.data?.people],
  );
  const locations = useMemo(
    () => optionsQuery.data?.locations ?? [],
    [optionsQuery.data?.locations],
  );
  const auditorOptions = useMemo(
    () => people.filter((person) => (person.auditor_roles || []).length > 0),
    [people],
  );
  const leadAuditorOptions = useMemo(
    () => auditorOptions.filter((person) => (person.auditor_roles || []).includes("LEAD_AUDITOR")),
    [auditorOptions],
  );
  const effectiveAuditScopeId =
    auditScopeId ||
    preferredScope(
      scopes,
      selectedCandidate?.programme.programme_kind || "INTERNAL",
    )?.id ||
    "";
  const selectedScope =
    scopes.find((scope) => scope.id === effectiveAuditScopeId) ?? null;
  const selectedAuditee =
    people.find((person) => person.id === auditeeUserId) ?? null;
  const locationArea =
    (source === "programme"
      ? selectedCandidate?.item.auditable_entity
      : null) ||
    (mode === "surveillance"
      ? { entity_type: "FACILITY" as const, display_label: surveillanceFocus }
      : null);
  const effectiveLocation =
    location || suggestedLocationCode(locationArea, locations);

  const chooseCandidate = (key: string) => {
    setProgrammeKey(key);
    const candidate = candidates.find((entry) => entry.key === key);
    if (!candidate) return;
    const date = candidateDate(candidate);
    const matchingScope = preferredScope(
      scopes,
      candidate.programme.programme_kind || "INTERNAL",
    );
    setAuditScopeId(matchingScope?.id || auditScopeId);
    setTitle(candidate.item.title);
    setScopeText(candidate.item.scope);
    setCriteria(programmeCriteria(candidate.item) || CRITERIA_OPTIONS[0]);
    setAuditeeUserId(candidate.item.auditee_user_id || "");
    setLeadAuditorUserId(
      candidate.item.lead_auditor_user_id || currentUser?.id || "",
    );
    setObserverAuditorUserId(candidate.item.observer_auditor_user_id || "");
    setSupportingAuditorUserIds(
      withoutLeadAuditor(
        candidate.item.supporting_auditor_user_ids || [],
        candidate.item.lead_auditor_user_id || currentUser?.id,
        candidate.item.observer_auditor_user_id,
      ),
    );
    setLocation(
      candidate.item.default_location ||
        suggestedLocationCode(candidate.item.auditable_entity, locations),
    );
    setPlannedStart(date);
    setPlannedEnd(
      endDateForDuration(date, candidate.item.default_duration_days),
    );
    setStartTime(candidate.item.default_start_time?.slice(0, 5) || "09:00");
    setEndTime(candidate.item.default_end_time?.slice(0, 5) || "17:00");
    setNotifyAuditors(candidate.item.notify_auditors ?? true);
    setNotifyAuditees(candidate.item.notify_auditees ?? true);
  };

  const surveillanceLabel =
    surveillanceFocus === "Other targeted compliance check"
      ? customSurveillanceFocus.trim()
      : surveillanceFocus;
  const resolvedTitle =
    mode === "surveillance"
      ? `Surveillance · ${surveillanceLabel}`
      : title.trim();
  const duplicateAudit =
    mode === "audit" && source === "programme"
      ? existingAudits.find(
          (audit) =>
            audit.status !== "CLOSED" &&
            audit.title.trim().toLowerCase() === resolvedTitle.toLowerCase() &&
            audit.planned_start === plannedStart,
        )
      : undefined;

  const endTimeOptions = TIME_OPTIONS.filter((value) => value > startTime);

  const launchMutation = useMutation({
    mutationFn: async () => {
      if (!selectedScope) throw new Error("Select an audit scope.");
      if (!resolvedTitle || resolvedTitle === "Surveillance ·")
        throw new Error("Enter the audit title or surveillance focus.");
      if (!plannedStart || !plannedEnd)
        throw new Error("Select the planned start and end dates.");
      if (plannedEnd < plannedStart)
        throw new Error("The end date cannot be before the start date.");
      if (plannedStart.slice(0, 4) !== plannedEnd.slice(0, 4))
        throw new Error("An audit cannot cross a calendar year.");
      if (endTime <= startTime)
        throw new Error("The end time must be after the start time.");
      if (!leadAuditorUserId) throw new Error("Select a lead auditor.");
      if (!effectiveLocation)
        throw new Error("Select a configured physical location.");
      if (source === "programme" && !selectedCandidate)
        throw new Error("Select a programme requirement.");
      if (duplicateAudit)
        throw new Error(
          "This programme audit is already open for the selected date.",
        );

      const created = await qmsCreateAudit({
        domain: "AMO",
        kind: selectedScope.default_kind as
          "INTERNAL" | "EXTERNAL" | "THIRD_PARTY",
        audit_scope_id: selectedScope.id,
        audit_scope_code: selectedScope.code,
        title: resolvedTitle,
        scope:
          mode === "surveillance"
            ? `Unscheduled surveillance of ${surveillanceLabel}.`
            : scopeText.trim() || resolvedTitle,
        criteria: mode === "surveillance" ? CRITERIA_OPTIONS[0] : criteria,
        auditee: selectedAuditee?.full_name || null,
        auditee_email: selectedAuditee?.email || null,
        auditee_user_id: selectedAuditee?.id || null,
        lead_auditor_user_id: leadAuditorUserId,
        observer_auditor_user_id: observerAuditorUserId || null,
        supporting_auditor_user_ids: withoutLeadAuditor(
          supportingAuditorUserIds,
          leadAuditorUserId,
          observerAuditorUserId,
        ),
        location: effectiveLocation || null,
        notify_auditors: mode === "audit" && notifyAuditors,
        notify_auditees: mode === "audit" && notifyAuditees,
        reminder_interval_days: 7,
        planned_start: plannedStart,
        planned_end: plannedEnd,
        planned_start_time: startTime,
        planned_end_time: endTime,
      });
      return mode === "surveillance" ? qmsStartAudit(created.id) : created;
    },
    onSuccess: (audit) =>
      onCreated(audit, {
        offerProgramme: mode === "audit" && source === "one-off",
      }),
    onError: (reason: Error) =>
      setError(reason.message || "The audit could not be created."),
  });

  return (
    <Drawer
      title={
        mode === "surveillance"
          ? "Start surveillance"
          : "Create scheduled audit"
      }
      isOpen={isOpen}
      onClose={onClose}
      closeDisabled={launchMutation.isPending}
      panelClassName="qa-audit-launch-drawer"
    >
      <form
        className="qa-audit-launch"
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          launchMutation.mutate();
        }}
      >
        <div
          className={`qa-audit-launch__purpose qa-audit-launch__purpose--${mode}`}
        >
          {mode === "surveillance" ? (
            <ShieldCheck size={19} aria-hidden />
          ) : (
            <CalendarPlus size={19} aria-hidden />
          )}
          <div>
            <strong>
              {mode === "surveillance"
                ? "Unscheduled inspection"
                : "Governed audit occurrence"}
            </strong>
            <span>
              {mode === "surveillance"
                ? "No advance auditee notice. Evidence and findings remain fully controlled."
                : "Set the occurrence once, then continue in the audit workspace."}
            </span>
          </div>
        </div>

        {mode === "audit" ? (
          <div
            className="qa-audit-launch__source"
            role="group"
            aria-label="Audit source"
          >
            <button
              type="button"
              className={source === "programme" ? "is-active" : ""}
              disabled={!candidates.length}
              onClick={() => setSource("programme")}
            >
              <ClipboardCheck size={16} aria-hidden /> From programme
            </button>
            <button
              type="button"
              className={source === "one-off" ? "is-active" : ""}
              onClick={() => {
                setSource("one-off");
                setTitle("");
                setScopeText("");
                setCriteria(CRITERIA_OPTIONS[0]);
              }}
            >
              <CalendarPlus size={16} aria-hidden /> One-off audit
            </button>
          </div>
        ) : null}

        {mode === "audit" && source === "programme" ? (
          <label className="qa-audit-launch__wide">
            Programme requirement
            <select
              value={programmeKey}
              onChange={(event) => chooseCandidate(event.target.value)}
            >
              <option value="">Select requirement</option>
              {candidates.map((candidate) => (
                <option key={candidate.key} value={candidate.key}>
                  {candidate.programme.programme_ref} · {candidate.item.title}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {mode === "audit" && source === "one-off" ? (
          <label className="qa-audit-launch__wide">
            Audit title
            <input
              value={title}
              maxLength={255}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="e.g. Hangar maintenance audit"
              autoFocus
            />
          </label>
        ) : null}

        {mode === "surveillance" ? (
          <>
            <label>
              Inspection focus
              <select
                value={surveillanceFocus}
                onChange={(event) => setSurveillanceFocus(event.target.value)}
              >
                {SURVEILLANCE_FOCUS_OPTIONS.map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
            </label>
            {surveillanceFocus === "Other targeted compliance check" ? (
              <label>
                Focus description
                <input
                  value={customSurveillanceFocus}
                  onChange={(event) =>
                    setCustomSurveillanceFocus(event.target.value)
                  }
                  placeholder="Area being inspected"
                />
              </label>
            ) : null}
          </>
        ) : null}

        <div className="qa-audit-launch__grid">
          <label>
            Audit scope
            <select
              value={effectiveAuditScopeId}
              onChange={(event) => setAuditScopeId(event.target.value)}
              disabled={scopesQuery.isLoading}
            >
              <option value="">
                {scopesQuery.isLoading ? "Loading scopes…" : "Select scope"}
              </option>
              {scopes.map((scope) => (
                <option key={scope.id} value={scope.id}>
                  {scope.code} · {scope.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Lead auditor
            <select
              value={leadAuditorUserId}
              onChange={(event) => {
                const lead = event.target.value;
                setLeadAuditorUserId(lead);
                if (observerAuditorUserId === lead)
                  setObserverAuditorUserId("");
                setSupportingAuditorUserIds((current) =>
                  withoutLeadAuditor(current, lead, observerAuditorUserId),
                );
              }}
              disabled={optionsQuery.isLoading}
            >
              <option value="">Select lead</option>
              {leadAuditorOptions.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.full_name}
                  {person.department_name ? ` · ${person.department_name}` : ""}
                </option>
              ))}
            </select>
          </label>
          <ProgrammeObserverSelect
            id="audit-launch-observer"
            people={auditorOptions}
            leadAuditorUserId={leadAuditorUserId}
            supportingAuditorUserIds={supportingAuditorUserIds}
            value={observerAuditorUserId}
            onChange={(observerUserId) => {
              setObserverAuditorUserId(observerUserId);
              setSupportingAuditorUserIds((current) =>
                withoutLeadAuditor(current, leadAuditorUserId, observerUserId),
              );
            }}
          />
          <label>
            Responsible area / auditee
            <select
              value={auditeeUserId}
              onChange={(event) => setAuditeeUserId(event.target.value)}
              disabled={optionsQuery.isLoading}
            >
              <option value="">Assign later</option>
              {people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.full_name}
                  {person.department_name ? ` · ${person.department_name}` : ""}
                </option>
              ))}
            </select>
          </label>
          <ProgrammeLocationSelect
            id="audit-launch-location"
            value={effectiveLocation}
            locations={locations}
            onChange={setLocation}
            required
          />
          <label>
            Criteria
            <select
              value={criteria}
              onChange={(event) => setCriteria(event.target.value)}
              disabled={source === "programme"}
            >
              {source === "programme" &&
              !CRITERIA_OPTIONS.includes(criteria) ? (
                <option value={criteria}>Programme criteria</option>
              ) : null}
              {CRITERIA_OPTIONS.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </label>
          <label>
            Start date
            <input
              type="date"
              min={todayIso()}
              value={plannedStart}
              onChange={(event) => {
                setPlannedStart(event.target.value);
                if (plannedEnd < event.target.value)
                  setPlannedEnd(event.target.value);
              }}
            />
          </label>
          <label>
            End date
            <input
              type="date"
              min={plannedStart || todayIso()}
              value={plannedEnd}
              onChange={(event) => setPlannedEnd(event.target.value)}
            />
          </label>
          <label>
            Start time
            <select
              value={startTime}
              onChange={(event) => {
                const next = event.target.value;
                setStartTime(next);
                if (endTime <= next)
                  setEndTime(
                    TIME_OPTIONS.find((value) => value > next) || "17:00",
                  );
              }}
            >
              {TIME_OPTIONS.slice(0, -1).map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </label>
          <label>
            End time
            <select
              value={endTime}
              onChange={(event) => setEndTime(event.target.value)}
            >
              {endTimeOptions.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </label>
        </div>

        <SupportingAuditorPicker
          id="audit-launch-supporting-auditors"
          people={auditorOptions}
          leadAuditorUserId={leadAuditorUserId}
          excludedUserIds={[observerAuditorUserId]}
          value={supportingAuditorUserIds}
          onChange={setSupportingAuditorUserIds}
        />

        {mode === "audit" && source === "one-off" ? (
          <label className="qa-audit-launch__wide">
            Scope
            <textarea
              value={scopeText}
              onChange={(event) => setScopeText(event.target.value)}
              placeholder="What will this audit cover?"
              rows={2}
            />
          </label>
        ) : null}

        {mode === "audit" ? (
          <div className="qa-audit-launch__checks">
            <label>
              <input
                type="checkbox"
                checked={notifyAuditors}
                onChange={(event) => setNotifyAuditors(event.target.checked)}
              />{" "}
              Notify audit team
            </label>
            <label>
              <input
                type="checkbox"
                checked={notifyAuditees}
                onChange={(event) => setNotifyAuditees(event.target.checked)}
              />{" "}
              Notify auditee
            </label>
          </div>
        ) : null}

        {duplicateAudit ? (
          <div className="qa-audit-launch__duplicate">
            <CheckCircle2 size={17} aria-hidden />
            <span>
              <strong>Already issued:</strong> {duplicateAudit.audit_ref} is
              open for this date.
            </span>
            <button
              type="button"
              onClick={() => onOpenExisting(duplicateAudit)}
            >
              Open audit
            </button>
          </div>
        ) : null}
        {scopesQuery.isError || optionsQuery.isError ? (
          <p className="qa-audit-launch__error" role="alert">
            Audit options could not be loaded. Close this panel and retry.
          </p>
        ) : null}
        {error ? (
          <p className="qa-audit-launch__error" role="alert">
            {error}
          </p>
        ) : null}

        <footer className="qa-audit-launch__footer">
          <span>
            {mode === "audit"
              ? `${durationDays(plannedStart, plannedEnd)} day audit · 09:00–17:00 operating window enforced`
              : "The surveillance opens directly in fieldwork."}
          </span>
          <div>
            <button
              type="button"
              onClick={onClose}
              disabled={launchMutation.isPending}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="is-primary"
              disabled={
                launchMutation.isPending ||
                Boolean(duplicateAudit) ||
                !selectedScope ||
                !leadAuditorUserId
              }
            >
              {mode === "surveillance" ? (
                <Play size={15} aria-hidden />
              ) : (
                <CalendarPlus size={15} aria-hidden />
              )}
              {launchMutation.isPending
                ? "Creating…"
                : mode === "surveillance"
                  ? "Start surveillance"
                  : "Create audit"}
            </button>
          </div>
        </footer>
      </form>
    </Drawer>
  );
};

export default AuditLaunchDrawer;
