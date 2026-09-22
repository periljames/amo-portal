import { describe, expect, it } from "vitest";

import {
  DEFAULT_PLANNER_PREFERENCES,
  expandPlannerOccurrences,
  isoDateKey,
  isAuditScheduleTemplate,
  isMultiDayPlannerEvent,
  layoutAllDaySpans,
  layoutTimedEvents,
  monthGridDays,
  movePlannerEvent,
  normalisePlannerEvent,
  plannerCategory,
  plannerEventDurationDays,
  plannerNowScrollTop,
  plannerPillCopy,
  plannerTone,
  requestRange,
  startOfWeek,
  visiblePlannerDays,
  type PlannerEvent,
} from "./qmsPlannerModel";

describe("QMS planner model", () => {
  it("opens the unscheduled rail by default", () => {
    expect(DEFAULT_PLANNER_PREFERENCES.leftRailOpen).toBe(true);
    expect(DEFAULT_PLANNER_PREFERENCES.inspectorOpen).toBe(false);
  });

  it("centers the now line in the visible canvas", () => {
    expect(plannerNowScrollTop({
      nowTopPx: 640,
      stickyOffsetPx: 120,
      viewportHeight: 600,
      maxScrollTop: 2000,
    })).toBe(562);
    expect(plannerNowScrollTop({
      nowTopPx: 0,
      stickyOffsetPx: 0,
      viewportHeight: 600,
      maxScrollTop: 100,
    })).toBe(0);
    expect(plannerNowScrollTop({
      nowTopPx: 5000,
      stickyOffsetPx: 0,
      viewportHeight: 400,
      maxScrollTop: 800,
    })).toBe(800);
  });

  it("builds a complete Monday-to-Sunday month grid", () => {
    const days = monthGridDays(new Date(2026, 6, 20));
    expect(days[0].getDay()).toBe(1);
    expect(days.at(-1)?.getDay()).toBe(0);
    expect(days.length % 7).toBe(0);
    expect(days.some((day) => day.getMonth() === 6 && day.getDate() === 31)).toBe(true);
  });

  it("starts weeks on Monday", () => {
    // 2026-07-22 is Wednesday → week starts Monday 20th.
    expect(isoDateKey(startOfWeek(new Date(2026, 6, 22)))).toBe("2026-07-20");
    expect(isoDateKey(startOfWeek(new Date(2026, 6, 20)))).toBe("2026-07-20");
    expect(isoDateKey(startOfWeek(new Date(2026, 6, 19)))).toBe("2026-07-13");
  });

  it("creates a configurable business-day span", () => {
    const days = visiblePlannerDays(new Date(2026, 6, 17), 5, true);
    expect(days).toHaveLength(5);
    expect(days.every((day) => day.getDay() !== 0 && day.getDay() !== 6)).toBe(true);
  });

  it("colour-codes audits, training and overdue urgency", () => {
    expect(plannerCategory({ module: "audits", event_type: "audit_planned", title: "Base audit" })).toBe("audits");
    expect(plannerTone({ module: "audits", event_type: "audit_planned", title: "Base audit" })).toBe("audit");
    expect(plannerCategory({ module: "training", event_type: "training_expiry", title: "DGR-REF expires" })).toBe("training");
    expect(plannerTone({ module: "training", event_type: "training_expiry", title: "DGR-REF expires" })).toBe("warning");
    expect(plannerTone({ module: "audits", event_type: "audit_planned", due_state: "overdue", title: "Late audit" })).toBe("danger");
    expect(plannerCategory({ title: "SMS-REF expires HW", event_type: "competence_expiry" })).toBe("training");
  });

  it("normalises mutable audit events and keeps expiry records read-only", () => {
    const audit = normalisePlannerEvent({
      id: "audits:audit:123:audit_planned",
      module: "audits",
      entity_type: "audit",
      entity_id: "123",
      event_type: "audit_planned",
      title: "QAR/MO/26/001 · Line audit",
      date: "2026-07-20",
      starts_at: "2026-07-20T09:00:00Z",
    }, true);
    expect(audit?.category).toBe("audits");
    expect(audit?.tone).toBe("audit");
    expect(audit?.canReschedule).toBe(true);

    const expiry = normalisePlannerEvent({
      id: "training:training_record:456:training_expiry",
      module: "training",
      entity_type: "training_record",
      entity_id: "456",
      event_type: "training_expiry",
      title: "DGR-REF expires · Hannah Wambui",
      date: "2026-07-30",
      due_state: "soon",
    }, true);
    expect(expiry?.category).toBe("training");
    expect(expiry?.tone).toBe("warning");
    expect(expiry?.canReschedule).toBe(false);
  });

  it("normalises datetime end dates and expands an inclusive multi-day range", () => {
    const audit = normalisePlannerEvent({
      id: "audit-1",
      module: "audits",
      entity_type: "audit",
      entity_id: "audit-1",
      event_type: "audit_planned",
      title: "Three-day audit",
      date: "2026-07-20",
      planned_end: "2026-07-22T17:00:00Z",
    }, true);

    expect(audit?.endDate).toBe("2026-07-22");
    const occurrences = expandPlannerOccurrences(audit ? [audit] : []);
    expect(occurrences.map(({ occurrenceDate, spanRole, spanLength }) => ({ occurrenceDate, spanRole, spanLength }))).toEqual([
      { occurrenceDate: "2026-07-20", spanRole: "start", spanLength: 3 },
      { occurrenceDate: "2026-07-21", spanRole: "middle", spanLength: 3 },
      { occurrenceDate: "2026-07-22", spanRole: "end", spanLength: 3 },
    ]);
  });

  it("derives an inclusive multi-day span from duration_days and preserves schedule version", () => {
    const schedule = normalisePlannerEvent({
      id: "schedule-1",
      module: "audits",
      entity_type: "audit_schedule",
      entity_id: "schedule-1",
      event_type: "audit_due",
      title: "Three-day scheduled audit",
      date: "2026-07-20",
      duration_days: 3,
      schedule_version: 4,
    }, true);

    expect(schedule?.endDate).toBe("2026-07-22");
    expect(schedule?.source.schedule_version).toBe(4);
    expect(expandPlannerOccurrences(schedule ? [schedule] : []).map((item) => item.occurrenceDate)).toEqual([
      "2026-07-20",
      "2026-07-21",
      "2026-07-22",
    ]);
  });

  it("labels schedule templates distinctly from live audits on calendar pills", () => {
    const schedule = normalisePlannerEvent({
      id: "schedule-1",
      module: "audits",
      entity_type: "audit_schedule",
      entity_id: "schedule-1",
      event_type: "audit_due",
      title: "Internal: Line stores",
      date: "2026-07-20",
      audit_title: "Line stores",
      kind: "Internal",
      audit_source: "schedule_template",
      lead_auditor_name: "Alex Lead",
    }, true);
    expect(schedule && isAuditScheduleTemplate(schedule)).toBe(true);
    expect(plannerPillCopy(schedule!)).toMatchObject({
      title: "Line stores",
      reference: "Schedule · Internal",
      lead: "Alex Lead",
    });

    const live = normalisePlannerEvent({
      id: "audit-1",
      module: "audits",
      entity_type: "audit",
      entity_id: "audit-1",
      event_type: "audit_planned",
      title: "QAR/MO/26/001 · Line audit",
      date: "2026-07-20",
      audit_ref: "QAR/MO/26/001",
      audit_title: "Line audit",
      lead_auditor_name: "Alex Lead",
    }, true);
    expect(live && isAuditScheduleTemplate(live)).toBe(false);
    expect(plannerPillCopy(live!)).toMatchObject({
      title: "Line audit",
      reference: "QAR/MO/26/001",
      lead: "Alex Lead",
    });
  });

  it("moves multi-day events by a date delta", () => {
    const original: PlannerEvent = {
      id: "1",
      module: "audits",
      entityType: "audit",
      entityId: "1",
      eventType: "audit_planned",
      title: "Audit",
      date: "2026-07-20",
      endDate: "2026-07-22",
      category: "audits",
      tone: "audit",
      canReschedule: true,
      source: {},
    };
    const moved = movePlannerEvent(original, "2026-07-27");
    expect(moved.date).toBe("2026-07-27");
    expect(moved.endDate).toBe("2026-07-29");
    expect(expandPlannerOccurrences([moved])).toHaveLength(3);
  });

  it("lays out a three-day all-day span once across visible week columns", () => {
    const span: PlannerEvent = {
      id: "span",
      module: "audits",
      entityType: "audit",
      entityId: "span",
      eventType: "audit_planned",
      title: "Three-day audit",
      date: "2026-07-21",
      endDate: "2026-07-23",
      category: "audits",
      tone: "audit",
      canReschedule: true,
      source: {},
    };
    const layouts = layoutAllDaySpans(
      [span],
      ["2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24"],
    );

    expect(layouts).toEqual([{ event: span, startIndex: 1, endIndex: 3, lane: 0 }]);
  });

  it("keeps timed audits out of the all-day lane", () => {
    const timed = normalisePlannerEvent({
      id: "audit-timed",
      module: "audits",
      entity_type: "audit",
      entity_id: "audit-timed",
      event_type: "audit_planned",
      title: "Timed audit",
      date: "2026-09-23",
      planned_end: "2026-09-23",
      starts_at: "2026-09-23T09:00:00+00:00",
      ends_at: "2026-09-23T15:00:00+00:00",
      meeting_count: 2,
    }, true);

    expect(timed?.startTime).toBe("09:00");
    expect(timed?.endTime).toBe("15:00");
    expect(layoutAllDaySpans([timed!], ["2026-09-23"])).toEqual([]);
    expect(layoutTimedEvents([timed!], 0, 24)).toHaveLength(1);
  });

  it("ignores stale ends_on that would inflate a one-day audit", () => {
    const audit = normalisePlannerEvent({
      id: "audit-1day",
      module: "audits",
      entity_type: "audit",
      entity_id: "audit-1day",
      event_type: "audit_planned",
      title: "One-day audit",
      date: "2026-09-23",
      planned_end: "2026-09-23",
      ends_on: "2026-09-24",
      start_time: "10:00",
      end_time: "14:00",
    }, true);

    expect(audit?.endDate).toBe("2026-09-23");
    expect(isMultiDayPlannerEvent(audit!)).toBe(false);
    expect(plannerEventDurationDays(audit!)).toBe(1);
  });

  it("places multi-day timed audits on the hour timeline, not the all-day lane", () => {
    const audit = normalisePlannerEvent({
      id: "audit-multi",
      module: "audits",
      entity_type: "audit",
      entity_id: "audit-multi",
      event_type: "audit_planned",
      title: "Two-day audit",
      date: "2026-09-23",
      planned_end: "2026-09-24",
      start_time: "09:00",
      end_time: "17:00",
    }, true);

    expect(isMultiDayPlannerEvent(audit!)).toBe(true);
    expect(audit?.startTime).toBe("09:00");
    expect(layoutAllDaySpans([audit!], ["2026-09-23", "2026-09-24", "2026-09-25"])).toEqual([]);
    expect(layoutTimedEvents([audit!], 0, 24)).toHaveLength(1);
  });

  it("stacks overlapping all-day spans and reuses lanes after a span ends", () => {
    const event = (id: string, date: string, endDate: string): PlannerEvent => ({
      id,
      module: "audits",
      entityType: "audit",
      entityId: id,
      eventType: "audit_planned",
      title: id,
      date,
      endDate,
      category: "audits",
      tone: "audit",
      canReschedule: true,
      source: {},
    });
    const layouts = layoutAllDaySpans(
      [
        event("first", "2026-07-20", "2026-07-22"),
        event("overlap", "2026-07-21", "2026-07-23"),
        event("later", "2026-07-23", "2026-07-24"),
      ],
      ["2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24"],
    );

    expect(layouts.map(({ event: row, lane }) => ({ id: row.id, lane }))).toEqual([
      { id: "first", lane: 0 },
      { id: "overlap", lane: 1 },
      { id: "later", lane: 0 },
    ]);
  });

  it("lays out overlapping timed events in real columns and clamps the visible window", () => {
    const event = (id: string, startTime: string, endTime: string): PlannerEvent => ({
      id,
      module: "audits",
      entityType: "audit",
      entityId: id,
      eventType: "audit_planned",
      title: id,
      date: "2026-07-20",
      startTime,
      endTime,
      category: "audits",
      tone: "audit",
      canReschedule: true,
      source: {},
    });
    const layouts = layoutTimedEvents([
      event("early", "04:30", "06:00"),
      event("left", "09:00", "10:30"),
      event("right", "09:30", "10:00"),
      event("later", "10:30", "11:00"),
      event("overnight", "22:30", "01:00"),
    ], 5, 23);

    expect(layouts.find((item) => item.event.id === "early")).toMatchObject({ topPx: 0, heightPx: 64 });
    expect(layouts.find((item) => item.event.id === "left")).toMatchObject({ columnIndex: 0, columnCount: 2 });
    expect(layouts.find((item) => item.event.id === "right")).toMatchObject({ columnIndex: 1, columnCount: 2 });
    expect(layouts.find((item) => item.event.id === "later")).toMatchObject({ columnIndex: 0, columnCount: 1 });
    expect(layouts.find((item) => item.event.id === "overnight")?.heightPx).toBe(32);
  });

  it("requests Monday-based week ranges and full month pads", () => {
    const ordinaryWeek = requestRange("week", new Date(2026, 6, 20), 4);
    const fridayFiveDaySpan = requestRange("week", new Date(2026, 6, 17), 5);
    const sevenDaySpan = requestRange("week", new Date(2026, 6, 20), 7);
    const month = requestRange("month", new Date(2026, 6, 20));

    expect(ordinaryWeek).toEqual({ start: "2026-07-20", end: "2026-07-23" });
    expect(fridayFiveDaySpan).toEqual({ start: "2026-07-17", end: "2026-07-23" });
    expect(sevenDaySpan).toEqual({ start: "2026-07-20", end: "2026-07-28" });
    expect(month.start).toBe("2026-06-29");
    expect(month.end).toBe("2026-08-02");
    expect(isoDateKey(new Date(2026, 6, 20))).toBe("2026-07-20");
  });
});
