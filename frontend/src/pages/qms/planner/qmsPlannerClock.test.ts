import { describe, expect, it } from "vitest";

import {
  plannerClockAt,
  plannerTimezoneLabel,
  plannerTimezoneOffsetMinutes,
} from "./qmsPlannerClock";

describe("plannerClockAt", () => {
  it("uses the supplied tenant timezone rather than the browser or process timezone", () => {
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

  it("supports tenant-configured fixed UTC offsets without relying on IANA tzdata", () => {
    const instant = new Date("2026-08-04T22:45:00.000Z");
    expect(plannerClockAt(instant, "UTC+05:30")).toEqual({
      dateKey: "2026-08-05",
      hour: 4,
      minute: 15,
    });
    expect(plannerClockAt(instant, "UTC-04:00")).toEqual({
      dateKey: "2026-08-04",
      hour: 18,
      minute: 45,
    });
  });
});

describe("planner timezone display", () => {
  it("derives UTC comparison offsets from the tenant zone including daylight saving time", () => {
    expect(plannerTimezoneOffsetMinutes("Europe/London", new Date("2026-01-15T12:00:00Z"))).toBe(0);
    expect(plannerTimezoneOffsetMinutes("Europe/London", new Date("2026-07-15T12:00:00Z"))).toBe(60);
    expect(plannerTimezoneLabel("Europe/London", new Date("2026-07-15T12:00:00Z"))).toBe("Europe/London · UTC+1");
  });

  it("renders fractional fixed offsets accurately", () => {
    expect(plannerTimezoneOffsetMinutes("UTC+05:30")).toBe(330);
    expect(plannerTimezoneLabel("UTC+05:30")).toBe("UTC+05:30 · UTC+5:30");
  });
});
