import { describe, expect, it } from "vitest";

import { moveIntervalToZonedDay, templateWindowInZone, zonedWallTimeToIso } from "./timezone";
import { monthBounds, newIdempotencyKey, resolveRosterCalendarUrls, weekBounds } from "./rosterUi";

describe("rostering timezone utilities", () => {
  it("converts Nairobi wall time to UTC", () => {
    const value = zonedWallTimeToIso(new Date(2026, 6, 21), "08:00", "Africa/Nairobi");
    expect(value).toBe("2026-07-21T05:00:00.000Z");
  });

  it("builds an overnight shift in the AMO timezone", () => {
    const value = templateWindowInZone(new Date(2026, 6, 21), "18:00", "06:00", "Africa/Nairobi");
    expect(value.starts_at).toBe("2026-07-21T15:00:00.000Z");
    expect(value.ends_at).toBe("2026-07-22T03:00:00.000Z");
    expect(value.planned_minutes).toBe(720);
  });

  it("moves an assignment to another AMO-local date without changing duration", () => {
    const value = moveIntervalToZonedDay(
      "2026-07-21T05:00:00.000Z",
      "2026-07-21T14:00:00.000Z",
      new Date(2026, 6, 24),
      "Africa/Nairobi",
    );
    expect(value.starts_at).toBe("2026-07-24T05:00:00.000Z");
    expect(value.ends_at).toBe("2026-07-24T14:00:00.000Z");
  });
});

describe("planner utilities", () => {
  it("returns a Monday to Sunday week", () => {
    const value = weekBounds(new Date(2026, 6, 21));
    expect(value.from).toBe("2026-07-20");
    expect(value.to).toBe("2026-07-26");
    expect(value.days).toHaveLength(7);
  });

  it("returns every calendar date in leap-year February", () => {
    const value = monthBounds(new Date(2028, 1, 14));
    expect(value.from).toBe("2028-02-01");
    expect(value.to).toBe("2028-02-29");
    expect(value.days).toHaveLength(29);
  });

  it("creates distinct command idempotency keys", () => {
    const first = newIdempotencyKey("publish");
    const second = newIdempotencyKey("publish");
    expect(first.startsWith("publish:")).toBe(true);
    expect(second.startsWith("publish:")).toBe(true);
    expect(first).not.toBe(second);
  });

  it("resolves calendar links without assuming feed_path is present", () => {
    expect(resolveRosterCalendarUrls({
      https_url: "http://localhost:8080/rostering/calendar/feed/token.ics",
      webcal_url: "",
      refresh_interval_minutes: 60,
      includes: [],
    }, { browserOrigin: "https://portal.example.test" })).toEqual({
      httpsUrl: "https://portal.example.test/rostering/calendar/feed/token.ics",
      webcalUrl: "webcal://portal.example.test/rostering/calendar/feed/token.ics",
      feedPath: "/rostering/calendar/feed/token.ics",
    });
  });

  it("returns a recoverable empty state for a status-only calendar payload", () => {
    expect(resolveRosterCalendarUrls({})).toBeNull();
  });
});
