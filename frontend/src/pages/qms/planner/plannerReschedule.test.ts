import { describe, expect, it } from "vitest";
import { parseScheduleConflictDetail, parseStaleScheduleDetail } from "./plannerReschedule";

describe("plannerReschedule parsers", () => {
  it("parses SCHEDULE_STALE from ApiClientError body.detail", () => {
    const detail = parseStaleScheduleDetail({
      body: {
        detail: {
          code: "SCHEDULE_STALE",
          message: "The schedule changed after the planner loaded. Refresh before moving it again.",
          expected_old_date: "2026-09-23",
          current_date: "2026-09-24",
          trace_id: "551259edc1ec",
        },
      },
    });
    expect(detail).toEqual({
      code: "SCHEDULE_STALE",
      message: "The schedule changed after the planner loaded. Refresh before moving it again.",
      expected_old_date: "2026-09-23",
      current_date: "2026-09-24",
      trace_id: "551259edc1ec",
    });
  });

  it("parses SCHEDULE_CONFLICT with available slots", () => {
    const detail = parseScheduleConflictDetail({
      body: {
        detail: {
          code: "SCHEDULE_CONFLICT",
          message: "Overlaps another audit.",
          proposed_start_time: "10:00",
          proposed_end_time: "14:00",
          conflicts: [
            {
              subject_type: "AUDIT",
              subject_id: "a1",
              title: "A-1 · Other",
              start_date: "2026-09-24",
              end_date: "2026-09-24",
              start_time: "10:00:00",
              end_time: "14:00:00",
              conflicting_user_ids: ["u1"],
              reason: "Responsible personnel or attendees overlap.",
            },
          ],
          available_slots: [
            { start_time: "09:00", end_time: "13:00", label: "09:00 – 13:00" },
            { start_time: "14:00", end_time: "18:00", label: "14:00 – 18:00" },
          ],
        },
      },
    });
    expect(detail?.code).toBe("SCHEDULE_CONFLICT");
    expect(detail?.conflicts).toHaveLength(1);
    expect(detail?.available_slots[0]?.label).toBe("09:00 – 13:00");
  });
});
