import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarRange, Layers3, UsersRound } from "lucide-react";

import { listShiftTemplates } from "../../../services/rostering";
import { createWorkPattern, listWorkPatterns } from "../../../services/workforce";
import type { ShiftTemplateRead } from "../../../types/rostering";
import type { PatternDayStatus, WorkPatternCreate, WorkPatternDayInput } from "../../../types/workforce";
import { errorMessage } from "../rosterUi";
import { RosterLoading } from "./RosterShell";
import { WorkforceBulkSetupPanel } from "./WorkforceBulkSetupPanel";

function statusFor(shift: ShiftTemplateRead): PatternDayStatus {
  if (!shift.counts_as_duty || shift.kind === "OFF") return "OFF";
  if (shift.kind === "STANDBY") return "STANDBY";
  if (shift.kind === "TRAINING") return "TRAINING";
  return "DUTY";
}

function minuteOfDay(value: string): number {
  const [hour, minute] = value.slice(0, 5).split(":").map(Number);
  return hour * 60 + minute;
}

function patternDay(index: number, shift: ShiftTemplateRead): WorkPatternDayInput {
  const start = shift.default_start_time?.slice(0, 5) || null;
  const end = shift.default_end_time?.slice(0, 5) || null;
  const spansNextDay = Boolean(start && end && minuteOfDay(end) <= minuteOfDay(start));
  let plannedMinutes = shift.duration_minutes || 0;
  if (!plannedMinutes && start && end) {
    const raw = minuteOfDay(end) - minuteOfDay(start);
    plannedMinutes = raw > 0 ? raw : raw + 24 * 60;
  }
  return {
    cycle_day_index: index,
    shift_template_id: shift.id,
    status: statusFor(shift),
    start_time_local: shift.counts_as_duty ? start : null,
    end_time_local: shift.counts_as_duty ? end : null,
    spans_next_day: shift.counts_as_duty ? spansNextDay : false,
    planned_minutes: shift.counts_as_duty ? plannedMinutes : 0,
  };
}

function safePatternCode(base: string, existing: Set<string>): string {
  const normalized = base.toUpperCase().replace(/[^A-Z0-9-]/g, "-").replace(/-+/g, "-").slice(0, 56);
  if (!existing.has(normalized)) return normalized;
  let suffix = 2;
  while (existing.has(`${normalized}-${suffix}`)) suffix += 1;
  return `${normalized}-${suffix}`;
}

function makeAlternatingPattern(
  name: string,
  code: string,
  normalDuty: ShiftTemplateRead,
  weekendDuty: ShiftTemplateRead,
  rest: ShiftTemplateRead,
  phase: "A" | "B",
  timezoneName: string,
): WorkPatternCreate {
  const schedule = new Map<number, ShiftTemplateRead>();

  if (phase === "A") {
    // Team A worked the immediately preceding cycle's second weekend. Give it
    // replacement rest first, then the first weekend off. It works the second
    // weekend and receives replacement rest at the start of the next cycle.
    [0, 1, 5, 6].forEach((index) => schedule.set(index, rest));
    [2, 3, 4, 7, 8, 9, 10, 11].forEach((index) => schedule.set(index, normalDuty));
    [12, 13].forEach((index) => schedule.set(index, weekendDuty));
  } else {
    // Team B works the first weekend, then receives replacement rest on the
    // next two cycle days and has the second weekend off.
    [0, 1, 2, 3, 4, 9, 10, 11].forEach((index) => schedule.set(index, normalDuty));
    [5, 6].forEach((index) => schedule.set(index, weekendDuty));
    [7, 8, 12, 13].forEach((index) => schedule.set(index, rest));
  }

  const days = Array.from({ length: 14 }, (_, index) => patternDay(index, schedule.get(index) || rest));
  return {
    code,
    name,
    description: `14-day paired group rotation using tenant-selected ${normalDuty.code}, ${weekendDuty.code} and ${rest.code} templates. Replacement rest follows the working weekend across the repeating cycle.`,
    cycle_length_days: 14,
    is_active: true,
    timezone_name: timezoneName,
    applicability: {
      auto_assign: false,
      department_ids: [],
      position_ids: [],
      contract_types: [],
      anchor_date: null,
      priority: 100,
    },
    days,
  };
}

export function GroupRotationPlanner({ canManagePatterns }: { canManagePatterns: boolean }) {
  const queryClient = useQueryClient();
  const shiftsQuery = useQuery({
    queryKey: ["rostering", "group-rotation", "shifts"],
    queryFn: () => listShiftTemplates(true),
    staleTime: 5 * 60_000,
  });
  const patternsQuery = useQuery({
    queryKey: ["rostering", "group-rotation", "patterns"],
    queryFn: () => listWorkPatterns(true),
    staleTime: 0,
  });
  const [normalDutyId, setNormalDutyId] = useState("");
  const [weekendDutyId, setWeekendDutyId] = useState("");
  const [restId, setRestId] = useState("");
  const [timezoneName, setTimezoneName] = useState("");
  const [label, setLabel] = useState("Weekend Rotation");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const shifts = shiftsQuery.data || [];
  const dutyCandidates = useMemo(
    () => shifts.filter((shift) => shift.is_active && shift.counts_as_duty),
    [shifts],
  );
  const restCandidates = useMemo(
    () => shifts.filter((shift) => shift.is_active && !shift.counts_as_duty),
    [shifts],
  );
  const normalDuty = dutyCandidates.find((shift) => shift.id === normalDutyId) || dutyCandidates[0] || null;
  const weekendCandidates = useMemo(
    () => dutyCandidates.filter((shift) => shift.id !== normalDuty?.id),
    [dutyCandidates, normalDuty?.id],
  );
  const selectedWeekend = weekendCandidates.find((shift) => shift.id === weekendDutyId)
    || weekendCandidates[0]
    || normalDuty;
  const rest = restCandidates.find((shift) => shift.id === restId) || restCandidates[0] || null;
  const configured = (shift: ShiftTemplateRead | null) => Boolean(
    shift && (!shift.counts_as_duty || shift.duration_minutes || (shift.default_start_time && shift.default_end_time)),
  );
  const existingCodes = new Set((patternsQuery.data || []).map((pattern) => pattern.code.toUpperCase()));
  const effectiveTimezone = timezoneName.trim() || (patternsQuery.data || []).find((pattern) => pattern.timezone_name)?.timezone_name || "";

  const createPair = async () => {
    if (!normalDuty || !rest || !selectedWeekend || !effectiveTimezone) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const base = `ALT-${selectedWeekend.code}`;
      const codeA = safePatternCode(`${base}-A`, existingCodes);
      existingCodes.add(codeA);
      const codeB = safePatternCode(`${base}-B`, existingCodes);
      await createWorkPattern(makeAlternatingPattern(`${label} · Team A`, codeA, normalDuty, selectedWeekend, rest, "A", effectiveTimezone));
      await createWorkPattern(makeAlternatingPattern(`${label} · Team B`, codeB, normalDuty, selectedWeekend, rest, "B", effectiveTimezone));
      await queryClient.invalidateQueries({ queryKey: ["rostering", "group-rotation", "patterns"] });
      await queryClient.invalidateQueries({ queryKey: ["workforce", "hr", "work-patterns"] });
      setMessage(`Created ${codeA} and ${codeB}. Assign each pattern below by department filter, all-matching group, or selected individuals.`);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  if (shiftsQuery.isPending || patternsQuery.isPending) return <RosterLoading label="Loading group rotation controls…" />;

  const missingTemplates = !normalDuty || !rest;
  const unconfiguredDuty = !configured(normalDuty) || !configured(selectedWeekend);

  return (
    <section className="wr-panel">
      <div className="rs-compact-heading">
        <div>
          <span className="wr-eyebrow">Group planning</span>
          <h2><Layers3 size={18} /> Alternating weekend teams</h2>
          <p>Create a paired 14-day Team A/Team B rotation from this tenant's own shift templates, then allocate it to a department, filtered group or selected employees.</p>
        </div>
      </div>

      {shiftsQuery.error || patternsQuery.error ? <div className="wr-inline-error">{errorMessage(shiftsQuery.error || patternsQuery.error)}</div> : null}
      {missingTemplates ? <div className="wr-inline-warning">Create at least one working template and one non-duty/rest template before building a group rotation. The portal does not require specific shift codes.</div> : null}
      {!missingTemplates && unconfiguredDuty ? <div className="wr-inline-warning">Configure start/end times or duration on the selected working templates before building the rotation. The planner does not invent shift times.</div> : null}
      {!effectiveTimezone ? <div className="wr-inline-warning">Enter the tenant/base operational IANA time zone before creating the rotation.</div> : null}
      {message ? <div className="wr-inline-success">{message}</div> : null}
      {error ? <div className="wr-inline-error">{error}</div> : null}

      <div className="wr-form-grid">
        <label>
          Rotation name
          <input value={label} onChange={(event) => setLabel(event.target.value)} maxLength={80} />
        </label>
        <label>
          Normal working template
          <select value={normalDuty?.id || ""} onChange={(event) => setNormalDutyId(event.target.value)}>
            {dutyCandidates.map((shift) => <option key={shift.id} value={shift.id}>{shift.code} · {shift.label}</option>)}
          </select>
        </label>
        <label>
          Working weekend template
          <select value={selectedWeekend?.id || ""} onChange={(event) => setWeekendDutyId(event.target.value)}>
            {weekendCandidates.length ? weekendCandidates.map((shift) => <option key={shift.id} value={shift.id}>{shift.code} · {shift.label}</option>) : normalDuty ? <option value={normalDuty.id}>{normalDuty.code} · {normalDuty.label}</option> : null}
          </select>
        </label>
        <label>
          Rest/off template
          <select value={rest?.id || ""} onChange={(event) => setRestId(event.target.value)}>
            {restCandidates.map((shift) => <option key={shift.id} value={shift.id}>{shift.code} · {shift.label}</option>)}
          </select>
        </label>
        <label>
          Operational time zone
          <input value={timezoneName} onChange={(event) => setTimezoneName(event.target.value)} placeholder={effectiveTimezone || "e.g. Africa/Nairobi"} maxLength={64} />
        </label>
      </div>

      <div className="wr-callout">
        <CalendarRange size={16} />
        <span>The two teams alternate working weekends. The generated cycle places replacement rest immediately after each team's working weekend, including across the 14-day cycle boundary. Final publication still runs the authoritative timestamp-based rest and duty validator.</span>
      </div>

      <button
        type="button"
        className="wr-button wr-button--primary"
        disabled={!canManagePatterns || busy || missingTemplates || unconfiguredDuty || !selectedWeekend || !label.trim() || !effectiveTimezone}
        onClick={() => void createPair()}
      >
        <UsersRound size={15} /> {busy ? "Creating paired patterns…" : "Create Team A / Team B patterns"}
      </button>

      <details className="wr-native-guidance" open>
        <summary>Assign patterns to groups or people</summary>
        <p>Filter by department for departmental allocation, select all matching personnel, exclude exceptions, or tick individual employees. Use pattern assignment only; contract changes remain a separate action.</p>
        <WorkforceBulkSetupPanel canManageContracts={false} canManagePatterns={canManagePatterns} />
      </details>
    </section>
  );
}
