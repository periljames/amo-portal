import { describe, expect, it } from "vitest";

import {
  buildQmsOverviewRoutes,
  deriveQmsOverviewHealth,
  normaliseActionQueue,
  normaliseQmsCalendarEntries,
  parseQmsDate,
  qmsOwnerStatusLabel,
  qmsRelativeDateLabel,
} from "./qmsOverviewModel";

describe("QMS overview decision model", () => {
  it("builds encoded canonical routes without legacy qms paths", () => {
    const routes = buildQmsOverviewRoutes("Safari Link/AMO");
    expect(routes.root).toBe("/maintenance/Safari%20Link%2FAMO/quality");
    expect(routes.calendar).toContain("/quality/calendar/week");
    expect(routes.overdueCars).toContain("/quality/cars/overdue");
    expect(routes.training).toContain("/training/competence/dashboard");
    expect(Object.values(routes).some((route) => route.includes("/qms"))).toBe(false);
  });

  it("uses the server priority and limits the action queue to five", () => {
    const rows = normaliseActionQueue([
      { id: "findings", label: "Findings", count: 8, route: "/findings", tone: "warning", priority: 60, next_action: "Review" },
      { id: "cars", label: "Overdue CARs", count: 2, route: "/cars", tone: "danger", priority: 100, next_action: "Review" },
      { id: "training", label: "Training", count: 3, route: "/training", tone: "danger", priority: 95, next_action: "Renew" },
      { id: "a", label: "A", count: 1, route: "/a", tone: "warning", priority: 50, next_action: "Open" },
      { id: "b", label: "B", count: 1, route: "/b", tone: "warning", priority: 40, next_action: "Open" },
      { id: "c", label: "C", count: 1, route: "/c", tone: "warning", priority: 30, next_action: "Open" },
      { id: "zero", label: "Zero", count: 0, route: "/zero", tone: "neutral", priority: 999, next_action: "Ignore" },
    ]);

    expect(rows.map((row) => row.id)).toEqual(["cars", "training", "findings", "a", "b"]);
  });

  it("derives health from ranked server actions and source completeness", () => {
    expect(deriveQmsOverviewHealth({ action_queue: [{ id: "x", label: "X", count: 2, route: "/x", tone: "danger", priority: 100, next_action: "Review" }], source_health: { status: "healthy", error_count: 0 } }).tone).toBe("danger");
    expect(deriveQmsOverviewHealth({ action_queue: [{ id: "x", label: "X", count: 2, route: "/x", tone: "warning", priority: 50, next_action: "Review" }], source_health: { status: "healthy", error_count: 0 } }).tone).toBe("warning");
    expect(deriveQmsOverviewHealth({ action_queue: [], source_health: { status: "partial", error_count: 1 } }).tone).toBe("neutral");
    expect(deriveQmsOverviewHealth({ action_queue: [], source_health: { status: "healthy", error_count: 0 } }).tone).toBe("positive");
  });

  it("treats date-only deadlines as local calendar dates", () => {
    const parsed = parseQmsDate("2026-07-31");
    expect(parsed?.getFullYear()).toBe(2026);
    expect(parsed?.getMonth()).toBe(6);
    expect(parsed?.getDate()).toBe(31);
  });

  it("filters past obligations and preserves calendar ordering", () => {
    const now = new Date(2026, 6, 31, 12, 0, 0);
    const rows = normaliseQmsCalendarEntries([
      { id: "later", title: "Later", date: "2026-08-04", module: "audits" },
      { id: "past", title: "Past", date: "2026-07-30", module: "cars" },
      { id: "today", title: "Today", date: "2026-07-31", module: "training" },
      { id: "invalid", title: "Invalid", date: "not-a-date", module: "reviews" },
    ], now);

    expect(rows.map((row) => row.id)).toEqual(["today", "later"]);
    expect(qmsRelativeDateLabel(rows[0].date, now)).toBe("Today");
    expect(qmsRelativeDateLabel(rows[1].date, now)).toBe("In 4 days");
  });

  it("presents owner state in operational language", () => {
    expect(qmsOwnerStatusLabel("partially_assigned")).toBe("Partly unassigned");
    expect(qmsOwnerStatusLabel("not_available")).toBe("Ownership unavailable");
  });
});
