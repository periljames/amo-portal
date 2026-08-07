import { describe, expect, it } from "vitest";

import {
  isoDateKey,
  monthGridDays,
  movePlannerEvent,
  normalisePlannerEvent,
  requestRange,
  visiblePlannerDays,
  type PlannerEvent,
} from "./qmsPlannerModel";

describe("QMS planner model", () => {
  it("builds a complete Sunday-to-Saturday month grid", () => {
    const days = monthGridDays(new Date(2026, 6, 20));
    expect(days[0].getDay()).toBe(0);
    expect(days.at(-1)?.getDay()).toBe(6);
    expect(days.length % 7).toBe(0);
    expect(days.some((day) => day.getMonth() === 6 && day.getDate() === 31)).toBe(true);
  });

  it("creates a configurable business-day span", () => {
    const days = visiblePlannerDays(new Date(2026, 6, 17), 5, true);
    expect(days).toHaveLength(5);
    expect(days.every((day) => day.getDay() !== 0 && day.getDay() !== 6)).toBe(true);
  });

  it("normalises mutable audit events and keeps expiry records read-only", () => {
    const audit = normalisePlannerEvent({
      id: "audits:audit:123:audit_planned",
      module: "audits",
      entity_type: "audit",
      entity_id: "123",
      event_type: "audit_planned",
      title: "QAR/MO/26/001 · Procurement audit",
      date: "2026-07-20",
    }, true);
    const expiry = normalisePlannerEvent({
      id: "training-competence:training_record:456:training_expiry",
      module: "training-competence",
      entity_type: "training_record",
      entity_id: "456",
      event_type: "training_expiry",
      title: "James Mugo · FTS-REF expires",
      date: "2026-07-22",
    }, true);

    expect(audit?.category).toBe("audits");
    expect(audit?.canReschedule).toBe(true);
    expect(expiry?.category).toBe("training");
    expect(expiry?.canReschedule).toBe(false);
  });

  it("preserves multi-day duration when an event moves", () => {
    const event: PlannerEvent = {
      id: "audits:audit:123:audit_planned",
      module: "audits",
      entityType: "audit",
      entityId: "123",
      eventType: "audit_planned",
      title: "Audit",
      date: "2026-07-20",
      endDate: "2026-07-22",
      startTime: null,
      endTime: null,
      link: null,
      dueState: "upcoming",
      status: "PLANNED",
      priority: null,
      ownerLabel: null,
      location: null,
      category: "audits",
      tone: "audit",
      canReschedule: true,
      source: {},
    };

    const moved = movePlannerEvent(event, "2026-07-27");
    expect(moved.date).toBe("2026-07-27");
    expect(moved.endDate).toBe("2026-07-29");
  });

  it("requests exact month ranges and covers both calendar and business-day timelines", () => {
    const ordinaryWeek = requestRange("week", new Date(2026, 6, 20), 4);
    const fridayFiveDaySpan = requestRange("week", new Date(2026, 6, 17), 5);
    const sevenDaySpan = requestRange("week", new Date(2026, 6, 20), 7);
    const month = requestRange("month", new Date(2026, 6, 20));

    expect(ordinaryWeek).toEqual({ start: "2026-07-20", end: "2026-07-23" });
    expect(fridayFiveDaySpan).toEqual({ start: "2026-07-17", end: "2026-07-23" });
    expect(sevenDaySpan).toEqual({ start: "2026-07-19", end: "2026-07-28" });
    expect(month.start).toBe("2026-06-28");
    expect(month.end).toBe("2026-08-01");
    expect(isoDateKey(new Date(2026, 6, 20))).toBe("2026-07-20");
  });
});