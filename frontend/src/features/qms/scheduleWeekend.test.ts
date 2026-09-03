import { describe, expect, it } from "vitest";

import {
  calendarEndIso,
  enumerateScheduleDays,
  formatScheduleRangeLabel,
  parseWeekendConfirmationDetail,
  scheduleSpansWeekend,
  weekendDatesInRange,
} from "./scheduleWeekend";

describe("scheduleWeekend", () => {
  it("detects a Fri–Mon style span that includes weekend days", () => {
    expect(scheduleSpansWeekend("2026-08-21", 4)).toBe(true); // Fri..Mon
    expect(weekendDatesInRange("2026-08-21", "2026-08-24")).toEqual(["2026-08-22", "2026-08-23"]);
  });

  it("does not flag a mid-week single day", () => {
    expect(scheduleSpansWeekend("2026-08-25", 1)).toBe(false);
    expect(calendarEndIso("2026-08-25", 3)).toBe("2026-08-27");
  });

  it("parses WEEKEND_CONFIRMATION_REQUIRED API errors", () => {
    const detail = parseWeekendConfirmationDetail({
      body: {
        detail: {
          code: "WEEKEND_CONFIRMATION_REQUIRED",
          message: "Base test audit runs into a weekend.",
          start_date: "2026-08-21",
          end_date: "2026-08-24",
          duration_days: 4,
          weekend_dates: ["2026-08-22", "2026-08-23"],
          options: {
            INCLUDE_WEEKEND: {
              label: "Include weekend",
              start_date: "2026-08-21",
              end_date: "2026-08-24",
            },
            SKIP_WEEKEND: {
              label: "Skip weekend",
              start_date: "2026-08-21",
              end_date: "2026-08-26",
            },
          },
          allowed_policies: ["INCLUDE_WEEKEND", "SKIP_WEEKEND"],
        },
      },
    });
    expect(detail?.code).toBe("WEEKEND_CONFIRMATION_REQUIRED");
    expect(detail?.options.SKIP_WEEKEND.end_date).toBe("2026-08-26");
  });

  it("parses WEEKEND_CONFIRMATION_REQUIRED embedded in legacy QMS Error messages", () => {
    const detail = parseWeekendConfirmationDetail(
      new Error(
        `QMS API 422: ${JSON.stringify({
          detail: {
            code: "WEEKEND_CONFIRMATION_REQUIRED",
            message: "Runs into a weekend.",
            start_date: "2026-08-14",
            end_date: "2026-08-16",
            duration_days: 3,
            weekend_dates: ["2026-08-15", "2026-08-16"],
            options: {
              INCLUDE_WEEKEND: { label: "Include", start_date: "2026-08-14", end_date: "2026-08-16" },
              SKIP_WEEKEND: { label: "Skip", start_date: "2026-08-14", end_date: "2026-08-18" },
            },
            allowed_policies: ["INCLUDE_WEEKEND", "SKIP_WEEKEND"],
          },
        })}`,
      ),
    );
    expect(detail?.code).toBe("WEEKEND_CONFIRMATION_REQUIRED");
    expect(detail?.options.SKIP_WEEKEND.end_date).toBe("2026-08-18");
  });

  it("enumerates day chips across a Fri–Sun span", () => {
    const days = enumerateScheduleDays("2026-08-14", "2026-08-16");
    expect(days.map((day) => `${day.weekdayShort}:${day.dayOfMonth}:${day.kind}`)).toEqual([
      "Fri:14:weekday",
      "Sat:15:weekend",
      "Sun:16:weekend",
    ]);
  });

  it("formats a readable skip range label", () => {
    expect(formatScheduleRangeLabel("2026-08-14", "2026-08-18")).toBe("Fri 14 Aug → Tue 18 Aug");
  });
});
