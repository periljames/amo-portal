import { useMemo, useState } from "react";
import { CheckCircle2, ChevronDown, ChevronUp, Layers3, RefreshCw, UsersRound } from "lucide-react";

import { apiJson, jsonBody } from "../../../services/typedApi";
import type { RosterPersonRead } from "../../../services/rosterPeople";
import type { WorkPatternAssignmentRead, WorkPatternRead } from "../../../types/workforce";
import { errorMessage } from "../rosterUi";
import "./cycle-start-batch-panel.css";

export type CycleStartOption = { value: string; label: string };

export type CycleStartCandidate = {
  person: RosterPersonRead;
  assignment: WorkPatternAssignmentRead;
  pattern: WorkPatternRead;
  targetDate: string;
  currentIndex: number;
  options: CycleStartOption[];
};

type BatchResponse = {
  batch_id: string;
  updated_count: number;
  unchanged_count: number;
  assignment_ids: string[];
};

type Group = {
  key: string;
  label: string;
  detail: string;
  candidates: CycleStartCandidate[];
  options: CycleStartOption[];
};

function rotationSignature(pattern: WorkPatternRead): string {
  const days = [...pattern.days]
    .sort((left, right) => left.cycle_day_index - right.cycle_day_index)
    .map((day) => [
      day.cycle_day_index,
      day.shift_template_id || "",
      day.status,
      day.start_time_local || "",
      day.end_time_local || "",
      day.spans_next_day ? 1 : 0,
      day.planned_minutes || 0,
    ].join(":"))
    .join("|");
  return `${pattern.cycle_length_days}::${pattern.timezone_name || "UTC"}::${days}`;
}

function groupLabel(candidates: CycleStartCandidate[], combineDepartments: boolean): { label: string; detail: string } {
  const departments = Array.from(new Set(candidates.map((row) => row.person.department_name || "Unassigned department")));
  const patterns = Array.from(new Set(candidates.map((row) => row.pattern.name)));
  const label = combineDepartments
    ? patterns.length === 1 ? patterns[0] : `${patterns.length} matching rotations`
    : `${departments[0]} · ${patterns.length === 1 ? patterns[0] : `${patterns.length} matching rotations`}`;
  const detail = combineDepartments
    ? `${departments.length} department${departments.length === 1 ? "" : "s"} · identical cycle sequence`
    : `Same department · identical cycle sequence`;
  return { label, detail };
}

export function CycleStartBatchPanel({
  candidates,
  disabled,
  onIndividualChange,
  onApplied,
  onError,
  onNotice,
}: {
  candidates: CycleStartCandidate[];
  disabled: boolean;
  onIndividualChange: (userId: string, cycleDayIndex: number) => Promise<void> | void;
  onApplied: () => Promise<void> | void;
  onError: (message: string | null) => void;
  onNotice: (message: string | null) => void;
}) {
  const [combineDepartments, setCombineDepartments] = useState(false);
  const [selectedByGroup, setSelectedByGroup] = useState<Record<string, string>>({});
  const [busyGroup, setBusyGroup] = useState<string | null>(null);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

  const groups = useMemo(() => {
    const bucket = new Map<string, CycleStartCandidate[]>();
    for (const candidate of candidates) {
      const signature = rotationSignature(candidate.pattern);
      const departmentKey = combineDepartments ? "all-departments" : candidate.person.department_id || "no-department";
      const key = `${signature}::${departmentKey}`;
      bucket.set(key, [...(bucket.get(key) || []), candidate]);
    }
    return Array.from(bucket.entries())
      .map(([key, rows]): Group => {
        const meta = groupLabel(rows, combineDepartments);
        return {
          key,
          label: meta.label,
          detail: meta.detail,
          candidates: rows.sort((left, right) => left.person.full_name.localeCompare(right.person.full_name)),
          options: rows[0]?.options || [],
        };
      })
      .sort((left, right) => right.candidates.length - left.candidates.length || left.label.localeCompare(right.label));
  }, [candidates, combineDepartments]);

  const applyGroup = async (group: Group) => {
    const fallbackIndex = group.candidates[0]?.currentIndex ?? 0;
    const cycleDayIndex = Number(selectedByGroup[group.key] ?? fallbackIndex);
    if (!Number.isInteger(cycleDayIndex) || cycleDayIndex < 0) return;
    setBusyGroup(group.key);
    onError(null);
    onNotice(null);
    try {
      const result = await apiJson<BatchResponse>("/workforce/work-pattern-assignments/cycle-starts/batch", {
        method: "POST",
        body: jsonBody({
          items: group.candidates.map((candidate) => ({
            assignment_id: candidate.assignment.id,
            target_date: candidate.targetDate,
          })),
          cycle_day_index: cycleDayIndex,
          reason: `Initial roster cycle start applied to ${group.candidates.length} personnel from controlled generator setup`,
        }),
      });
      await onApplied();
      onNotice(
        `${result.updated_count} cycle start${result.updated_count === 1 ? "" : "s"} updated${result.unchanged_count ? `; ${result.unchanged_count} already matched` : ""}.`,
      );
    } catch (cause) {
      onError(errorMessage(cause));
    } finally {
      setBusyGroup(null);
    }
  };

  return (
    <section className="wr-generation-starts wr-cycle-start-batch" aria-labelledby="wr-generation-starts-title">
      <div className="wr-generation-starts__head">
        <div>
          <strong id="wr-generation-starts-title">Auto set similar starting shifts</strong>
          <p>Personnel are grouped only when their complete shift rotation is identical. Department grouping is kept by default so a first setup remains reviewable even with thousands of employees.</p>
        </div>
        <span className="wr-pill wr-pill--info">{candidates.length} first setup</span>
      </div>

      <div className="wr-cycle-start-batch__toolbar">
        <label className="wr-cycle-start-batch__toggle">
          <input
            type="checkbox"
            checked={combineDepartments}
            disabled={disabled || Boolean(busyGroup)}
            onChange={(event) => {
              setCombineDepartments(event.target.checked);
              setExpandedGroup(null);
            }}
          />
          <span><Layers3 size={14} /> Combine departments when the rotation is identical</span>
        </label>
        <small>{groups.length} compatible group{groups.length === 1 ? "" : "s"}</small>
      </div>

      <div className="wr-cycle-start-batch__groups">
        {groups.map((group) => {
          const sameCurrentIndex = group.candidates.every((candidate) => candidate.currentIndex === group.candidates[0]?.currentIndex);
          const defaultValue = String(sameCurrentIndex ? group.candidates[0]?.currentIndex ?? 0 : group.candidates[0]?.currentIndex ?? 0);
          const selected = selectedByGroup[group.key] ?? defaultValue;
          const expanded = expandedGroup === group.key;
          return (
            <article key={group.key} className="wr-cycle-start-batch__group">
              <div className="wr-cycle-start-batch__group-main">
                <div className="wr-cycle-start-batch__identity">
                  <UsersRound size={16} />
                  <span><strong>{group.label}</strong><small>{group.candidates.length} personnel · {group.detail}</small></span>
                </div>
                <label>
                  <span>Starting shift</span>
                  <select
                    aria-label={`Starting shift for ${group.label}`}
                    value={selected}
                    disabled={disabled || Boolean(busyGroup)}
                    onChange={(event) => setSelectedByGroup((current) => ({ ...current, [group.key]: event.target.value }))}
                  >
                    {group.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
                <button
                  type="button"
                  className="wr-button wr-button--primary wr-button--small"
                  disabled={disabled || Boolean(busyGroup)}
                  onClick={() => void applyGroup(group)}
                >
                  {busyGroup === group.key ? <RefreshCw size={14} className="is-spinning" /> : <CheckCircle2 size={14} />}
                  {busyGroup === group.key ? "Applying…" : `Apply to all ${group.candidates.length}`}
                </button>
                <button
                  type="button"
                  className="wr-button wr-button--secondary wr-button--small"
                  disabled={disabled || Boolean(busyGroup)}
                  aria-expanded={expanded}
                  onClick={() => setExpandedGroup(expanded ? null : group.key)}
                >
                  {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  Review individuals
                </button>
              </div>

              {expanded ? (
                <div className="wr-generation-starts__list wr-cycle-start-batch__individuals">
                  {group.candidates.map((candidate) => (
                    <label key={candidate.person.user_id}>
                      <span><strong>{candidate.person.full_name}</strong><small>{candidate.pattern.name}</small></span>
                      <select
                        aria-label={`Initial shift for ${candidate.person.full_name}`}
                        value={String(candidate.currentIndex)}
                        disabled={disabled || Boolean(busyGroup)}
                        onChange={(event) => void onIndividualChange(candidate.person.user_id, Number(event.target.value))}
                      >
                        {candidate.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                      </select>
                    </label>
                  ))}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
