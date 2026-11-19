import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dateState } from "./QmsDailyFocus";

function localDateKey(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return year + "-" + month + "-" + day;
}

describe("My Quality Work daily focus date semantics", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("ranks personal UTC/offset timestamps by the local calendar day, not the ISO date prefix", () => {
    vi.setSystemTime(new Date("2026-11-19T12:00:00Z"));
    for (const instant of [
      "2026-11-18T23:30:00-03:00",
      "2026-11-18T22:30:00Z",
      "2026-11-20T00:30:00+05:00",
    ]) {
      const localDay = localDateKey(new Date(instant));
      expect(dateState(instant)).toEqual(dateState(localDay));
    }
  });

  it("keeps date-only governed deadlines as calendar dates with no timezone shift", () => {
    vi.setSystemTime(new Date("2026-11-19T12:00:00Z"));
    const today = localDateKey(new Date());
    expect(dateState(today)).toMatchObject({ rank: 1, label: "Due today", overdue: false });
    expect(dateState(null)).toMatchObject({ rank: 3, overdue: false });
    expect(dateState("not a date")).toMatchObject({ rank: 3, label: "Due date not available" });
  });
});
