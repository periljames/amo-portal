import { describe, expect, it } from "vitest";

import {
  buildQmsExposureSignals,
  buildQmsOverviewRoutes,
  deriveQmsOverviewHealth,
  normaliseQmsCalendarEntries,
  qmsRelativeDateLabel,
} from "./qmsOverviewModel";

describe("QMS overview decision model", () => {
  it("builds encoded canonical routes without using legacy qms paths", () => {
    const routes = buildQmsOverviewRoutes("Safari Link/AMO");

    expect(routes.root).toBe("/maintenance/Safari%20Link%2FAMO/quality");
    expect(routes.overdueCars).toContain("/quality/cars/overdue");
    expect(routes.training).toContain("/training/competence/dashboard");
    expect(Object.values(routes).some((route) => route.includes("/qms"))).toBe(false);
  });

  it("ranks overdue control exceptions ahead of upcoming work", () => {
    const routes = buildQmsOverviewRoutes("safarilink");
    const signals = buildQmsExposureSignals(
      {
        open_findings: 12,
        cars_due_soon: 4,
        overdue_cars: 2,
        training_expired_records: 3,
        draft_documents: 8,
      },
      routes,
    );

    expect(signals.map((signal) => signal.id)).toEqual([
      "overdue-cars",
      "expired-training",
      "cars-due-soon",
      "open-findings",
      "draft-documents",
    ]);
    expect(signals[0].tone).toBe("danger");
    expect(signals[0].count).toBe(2);
  });

  it("distinguishes urgent, attention, and clear dashboard states", () => {
    expect(deriveQmsOverviewHealth({ overdue_cars: 1 }).tone).toBe("danger");
    expect(deriveQmsOverviewHealth({ audits_due_soon: 2 }).tone).toBe("warning");
    expect(deriveQmsOverviewHealth({}).tone).toBe("positive");
  });

  it("filters invalid and past calendar rows before sorting upcoming obligations", () => {
    const now = new Date("2026-07-31T12:00:00");
    const rows = normaliseQmsCalendarEntries(
      [
        { id: "later", title: "Later", date: "2026-08-04", module: "audits" },
        { id: "past", title: "Past", date: "2026-07-30", module: "cars" },
        { id: "today", title: "Today", date: "2026-07-31", module: "training" },
        { id: "invalid", title: "Invalid", date: "not-a-date", module: "reviews" },
      ],
      now,
    );

    expect(rows.map((row) => row.id)).toEqual(["today", "later"]);
    expect(qmsRelativeDateLabel(rows[0].date, now)).toBe("Today");
    expect(qmsRelativeDateLabel(rows[1].date, now)).toBe("In 4 days");
  });
});
