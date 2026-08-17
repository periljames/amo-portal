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
  weekday: ShiftTemplateRead,
  weekendDuty: ShiftTemplateRead,
  rest: ShiftTemplateRead,
  phase: "A" | "B",
  timezoneName: string,
): WorkPatternCreate {
  const days: WorkPatternDayInput[] = [];
  for (const index of [0, 1, 2, 3, 4, 7, 8, 9, 10, 11]) days.push(patternDay(index, weekday));
  const firstWeekend = phase === "A" ? rest : weekendDuty;
  const secondWeekend = phase === "A" ? weekendDuty : rest;
  days.push(patternDay(5, firstWeekend), patternDay(6, firstWeekend));
  days.push(patternDay(12, secondWeekend), patternDay(13, secondWeekend));
  return {
    code,
    name,
    description: `14-day paired group rotation. ${phase === "A" ? "First" : "Second"} weekend is protected rest; alternate weekend uses ${weekendDuty.code}.`,
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
    days: days.sort((left, right) => left.cycle_day_index - right.cycle_day_index),
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
  const [weekendDutyId, setWeekendDutyId] = useState("");
  const [label, setLabel] = useState("Weekend Rotation");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const shifts = shiftsQuery.data || [];
  const weekday = shifts.find((shift) => shift.is_active && shift.code.toUpperCase() === "D") || null;
  const rest = shifts.find((shift) => shift.is_active && shift.code.toUpperCase() === "RD") || null;
  const weekendCandidates = useMemo(
    () => shifts.filter((shift) => shift.is_active && shift.counts_as_duty && shift.id !== weekday?.id),
    [shifts, weekday?.id],
  );
  const selectedWeekend = weekendCandidates.find((shift) => shift.id === weekendDutyId)
    || weekendCandidates.find((shift) => shift.code.toUpperCase() === "X")
    || weekendCandidates[0]
    || null;
  const configured = (shift: ShiftTemplateRead | null) => Boolean(
    shift && (!shift.counts_as_duty || shift.duration_minutes || (shift.default_start_time && shift.default_end_time)),
  );
  const existingCodes = new Set((patternsQuery.data || []).map((pattern) => pattern.code.toUpperCase()));
  const timezoneName = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

  const createPair = async () => {
    if (!weekday || !rest || !selectedWeekend) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const base = `ALT-${selectedWeekend.code}`;
      const codeA = safePatternCode(`${base}-A`, existingCodes);
      existingCodes.add(codeA);
      const codeB = safePatternCode(`${base}-B`, existingCodes);
      await createWorkPattern(makeAlternatingPattern(`${label} · Team A`, codeA, weekday, selectedWeekend, rest, "A", timezoneName));
      await createWorkPattern(makeAlternatingPattern(`${label} · Team B`, codeB, weekday, selectedWeekend, rest, "B", timezoneName));
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

  const missingCanonical = !weekday || !rest;
  const unconfiguredDuty = !configured(weekday) || !configured(selectedWeekend);

  return (
    <section className="wr-panel">
      <div className="rs-compact-heading">
        <div>
          <span className="wr-eyebrow">Group planning</span>
          <h2><Layers3 size={18} /> Alternating weekend teams</h2>
          <p>Create a paired 14-day Team A/Team B rotation, then allocate it to a department, filtered group or selected employees in one bulk action.</p>
        </div>
      </div>

      {shiftsQuery.error || patternsQuery.error ? <div className="wr-inline-error">{errorMessage(shiftsQuery.error || patternsQuery.error)}</div> : null}
      {missingCanonical ? <div className="wr-inline-warning">Create the canonical D and RD templates first. D remains normal day duty; RD is the single protected-rest code.</div> : null}
      {!missingCanonical && unconfiguredDuty ? <div className="wr-inline-warning">Configure start/end times (or duration) on D and the selected working/standby template before building the rotation. The planner does not hard-code shift times.</div> : null}
      {message ? <div className="wr-inline-success">{message}</div> : null}
      {error ? <div className="wr-inline-error">{error}</div> : null}

      <div className="wr-form-grid">
        <label>
          Rotation name
          <input value={label} onChange={(event) => setLabel(event.target.value)} maxLength={80} />
        </label>
        <label>
          Working weekend code
          <select value={selectedWeekend?.id || ""} onChange={(event) => setWeekendDutyId(event.target.value)}>
            {weekendCandidates.map((shift) => <option key={shift.id} value={shift.id}>{shift.code} · {shift.label}</option>)}
          </select>
        </label>
      </div>

      <div className="wr-callout">
        <CalendarRange size={16} />
        <span><strong>Team A:</strong> RD/RD → duty/duty. <strong>Team B:</strong> duty/duty → RD/RD. Weekdays use the configured D template. Choose X for Line, XH for Hangar, or any tenant-created working/standby template.</span>
      </div>

      <button
        type="button"
        className="wr-button wr-button--primary"
        disabled={!canManagePatterns || busy || missingCanonical || unconfiguredDuty || !selectedWeekend || !label.trim()}
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
