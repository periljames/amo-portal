import React, { useMemo, useState } from "react";
import { ArrowRight, CalendarDays } from "lucide-react";

import {
  enumerateScheduleDays,
  formatScheduleRangeLabel,
  type ScheduleDayChip,
  type WeekendConfirmationDetail,
  type WeekendPolicy,
} from "./scheduleWeekend";
import "./schedule-weekend-confirm.css";

type Props = {
  detail: WeekendConfirmationDetail;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: (policy: WeekendPolicy) => void;
};

type PreviewMode = "proposed" | WeekendPolicy;

function DayStrip({
  days,
  mode,
  weekendSet,
  activeSet,
}: {
  days: ScheduleDayChip[];
  mode: PreviewMode;
  weekendSet: Set<string>;
  activeSet: Set<string>;
}) {
  const lastWeekendIso = [...weekendSet].sort().at(-1) ?? "";

  return (
    <ol className={`qms-weekend-confirm__strip is-${mode.toLowerCase()}`} aria-hidden="true">
      {days.map((day, index) => {
        const isWeekendHit = weekendSet.has(day.iso) || day.kind === "weekend";
        const isActive = activeSet.has(day.iso);
        const isSkippedWeekend = mode === "SKIP_WEEKEND" && isWeekendHit && !isActive;
        const isRolledWeekday =
          mode === "SKIP_WEEKEND"
          && isActive
          && day.kind === "weekday"
          && Boolean(lastWeekendIso)
          && day.iso > lastWeekendIso;

        let state = "muted";
        if (isSkippedWeekend) state = "skipped";
        else if (isActive && isWeekendHit && mode !== "SKIP_WEEKEND") state = "weekend-work";
        else if (isRolledWeekday) state = "rolled";
        else if (isActive) state = "work";

        return (
          <li
            key={`${mode}-${day.iso}`}
            className={`qms-weekend-confirm__day is-${state}`}
            style={{ animationDelay: `${index * 45}ms` }}
          >
            <span className="qms-weekend-confirm__day-name">{day.weekdayShort}</span>
            <strong className="qms-weekend-confirm__day-num">{day.dayOfMonth}</strong>
          </li>
        );
      })}
    </ol>
  );
}

export default function ScheduleWeekendConfirmDialog({ detail, busy = false, onCancel, onConfirm }: Props) {
  const [preview, setPreview] = useState<PreviewMode>("proposed");

  const weekendSet = useMemo(() => new Set(detail.weekend_dates), [detail.weekend_dates]);

  const proposedDays = useMemo(
    () => enumerateScheduleDays(detail.start_date, detail.end_date),
    [detail.start_date, detail.end_date],
  );
  const skipDays = useMemo(
    () => enumerateScheduleDays(detail.options.SKIP_WEEKEND.start_date, detail.options.SKIP_WEEKEND.end_date),
    [detail.options.SKIP_WEEKEND.start_date, detail.options.SKIP_WEEKEND.end_date],
  );

  const stripDays = useMemo(() => {
    if (preview === "SKIP_WEEKEND") {
      const byIso = new Map<string, ScheduleDayChip>();
      for (const day of [...proposedDays, ...skipDays]) byIso.set(day.iso, day);
      return [...byIso.values()].sort((a, b) => a.iso.localeCompare(b.iso));
    }
    return proposedDays;
  }, [preview, proposedDays, skipDays]);

  const activeSet = useMemo(() => {
    if (preview === "SKIP_WEEKEND") return new Set(skipDays.map((day) => day.iso));
    return new Set(proposedDays.map((day) => day.iso));
  }, [preview, proposedDays, skipDays]);

  const previewRange =
    preview === "SKIP_WEEKEND"
      ? formatScheduleRangeLabel(detail.options.SKIP_WEEKEND.start_date, detail.options.SKIP_WEEKEND.end_date)
      : formatScheduleRangeLabel(detail.start_date, detail.end_date);

  return (
    <div
      className="qms-weekend-confirm-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target && !busy) onCancel();
      }}
    >
      <section className="qms-weekend-confirm" role="dialog" aria-modal="true" aria-labelledby="qms-weekend-confirm-title">
        <header>
          <div>
            <span>Weekend schedule confirmation</span>
            <strong id="qms-weekend-confirm-title">Does this activity run on the weekend?</strong>
          </div>
          <button type="button" aria-label="Close weekend confirmation" onClick={onCancel} disabled={busy}>
            ×
          </button>
        </header>

        <div className="qms-weekend-confirm__message">
          <CalendarDays size={16} />
          <span>{detail.message}</span>
        </div>

        <div className="qms-weekend-confirm__visual" aria-live="polite">
          <div className="qms-weekend-confirm__visual-meta">
            <span>{preview === "SKIP_WEEKEND" ? "After skipping weekend" : "Proposed window"}</span>
            <strong>{previewRange}</strong>
          </div>
          <DayStrip days={stripDays} mode={preview} weekendSet={weekendSet} activeSet={activeSet} />
          {preview === "SKIP_WEEKEND" ? (
            <p className="qms-weekend-confirm__visual-hint">
              <ArrowRight size={14} aria-hidden />
              Weekend days drop out; remaining workdays continue into the next week.
            </p>
          ) : (
            <p className="qms-weekend-confirm__visual-hint">
              Highlighted weekend days fall inside this window. Hover an option below to preview the shift.
            </p>
          )}
        </div>

        <div className="qms-weekend-confirm__choices">
          <button
            type="button"
            className={`qms-weekend-confirm__choice${preview === "INCLUDE_WEEKEND" ? " is-preview" : ""}`}
            disabled={busy}
            onMouseEnter={() => setPreview("INCLUDE_WEEKEND")}
            onFocus={() => setPreview("INCLUDE_WEEKEND")}
            onMouseLeave={() => setPreview("proposed")}
            onBlur={() => setPreview("proposed")}
            onClick={() => onConfirm("INCLUDE_WEEKEND")}
          >
            <strong>{detail.options.INCLUDE_WEEKEND.label}</strong>
            <small>
              {formatScheduleRangeLabel(detail.options.INCLUDE_WEEKEND.start_date, detail.options.INCLUDE_WEEKEND.end_date)}
            </small>
          </button>
          <button
            type="button"
            className={`qms-weekend-confirm__choice is-skip${preview === "SKIP_WEEKEND" ? " is-preview" : ""}`}
            disabled={busy}
            onMouseEnter={() => setPreview("SKIP_WEEKEND")}
            onFocus={() => setPreview("SKIP_WEEKEND")}
            onMouseLeave={() => setPreview("proposed")}
            onBlur={() => setPreview("proposed")}
            onClick={() => onConfirm("SKIP_WEEKEND")}
          >
            <strong>{detail.options.SKIP_WEEKEND.label}</strong>
            <small>
              {formatScheduleRangeLabel(detail.options.SKIP_WEEKEND.start_date, detail.options.SKIP_WEEKEND.end_date)}
            </small>
          </button>
        </div>

        <footer>
          <button type="button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        </footer>
      </section>
    </div>
  );
}
