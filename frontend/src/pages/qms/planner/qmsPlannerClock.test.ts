import { describe, expect, it } from "vitest";

import { plannerClockAt } from "./qmsPlannerClock";

describe("plannerClockAt", () => {
  it("uses Africa/Nairobi rather than the browser or process timezone", () => {
    const instant = new Date("2026-08-04T12:52:00.000Z");
    expect(plannerClockAt(instant, "Africa/Nairobi")).toEqual({
      dateKey: "2026-08-04",
      hour: 15,
      minute: 52,
    });
    expect(plannerClockAt(instant, "America/Los_Angeles")).toEqual({
      dateKey: "2026-08-04",
      hour: 5,
      minute: 52,
    });
  });

  it("uses the displayed timezone date across midnight", () => {
    const instant = new Date("2026-08-04T22:30:00.000Z");
    expect(plannerClockAt(instant, "Africa/Nairobi")).toEqual({
      dateKey: "2026-08-05",
      hour: 1,
      minute: 30,
    });
    expect(plannerClockAt(instant, "UTC")).toEqual({
      dateKey: "2026-08-04",
      hour: 22,
      minute: 30,
    });
  });
});
