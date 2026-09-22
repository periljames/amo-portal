import { describe, expect, it } from "vitest";

import { competenceChipStatus, earliestCompetenceValidUntil, capPrivilegeExpiresOn } from "./qmsPeopleCompetence";
import type { QmsEligibility } from "../../services/qmsPeople";

function training(partial: Partial<QmsEligibility["training"]>): QmsEligibility["training"] {
  return {
    required: ["QMS-INIT", "QMS-REF"],
    satisfied: [],
    missing: [],
    expired: [],
    records: [],
    expired_records: [],
    tracked_records: [],
    passed: false,
    ...partial,
  };
}

describe("competenceChipStatus", () => {
  it("shows INIT completion date from tracked Training history", () => {
    const chip = competenceChipStatus(
      "QMS-INIT",
      training({
        satisfied: ["QMS-INIT"],
        passed: true,
        tracked_records: [
          {
            course_code: "QMS-INIT",
            completion_date: "2025-01-15",
            valid_until: null,
            verification_status: "VERIFIED",
            record_status: "READY",
          },
        ],
      }),
    );
    expect(chip.tone).toBe("pass");
    expect(chip.detail.toLowerCase()).toContain("completed");
    expect(chip.detail).toMatch(/15/);
  });

  it("shows REF expiry and days-until-due when under 90 days", () => {
    const inThirty = new Date();
    inThirty.setHours(0, 0, 0, 0);
    inThirty.setDate(inThirty.getDate() + 30);
    const until = inThirty.toISOString().slice(0, 10);
    const chip = competenceChipStatus(
      "QMS-REF",
      training({
        satisfied: ["QMS-REF"],
        passed: true,
        tracked_records: [
          {
            course_code: "QMS-REF",
            completion_date: "2025-06-01",
            valid_until: until,
            days_until_expiry: 30,
            verification_status: "VERIFIED",
            record_status: "READY",
          },
        ],
      }),
    );
    expect(chip.tone).toBe("pass");
    expect(chip.detail.toLowerCase()).toContain("30 day");
  });

  it("does not leave REF blank when INIT satisfies currency but REF is also on file", () => {
    const chip = competenceChipStatus(
      "QMS-REF",
      training({
        satisfied: ["QMS-INIT"],
        passed: true,
        missing: [],
        tracked_records: [
          {
            course_code: "QMS-INIT",
            completion_date: "2024-03-01",
            verification_status: "VERIFIED",
            record_status: "READY",
          },
          {
            course_code: "QMS-REF",
            completion_date: "2025-08-01",
            valid_until: "2026-08-01",
            days_until_expiry: 200,
            verification_status: "VERIFIED",
            record_status: "READY",
          },
        ],
      }),
    );
    expect(chip.detail).not.toBe("—");
    expect(chip.detail).not.toBe("not recorded");
    expect(chip.detail.toLowerCase()).toContain("expires");
  });

  it("shows pending ADMIN without certificate as on-file data instead of blank", () => {
    const inYear = new Date();
    inYear.setHours(0, 0, 0, 0);
    inYear.setFullYear(inYear.getFullYear() + 1);
    const until = inYear.toISOString().slice(0, 10);
    const chip = competenceChipStatus(
      "QMS-ADMIN",
      training({
        admin: {
          status: "pending_or_inactive",
          course_code: "QMS-ADMIN",
          record: {
            course_code: "QMS-ADMIN",
            completion_date: "2025-02-01",
            valid_until: until,
            days_until_expiry: 365,
            verification_status: "PENDING",
            record_status: "PENDING",
          },
        },
        tracked_records: [
          {
            course_code: "QMS-ADMIN",
            completion_date: "2025-02-01",
            valid_until: until,
            days_until_expiry: 365,
            verification_status: "PENDING",
            record_status: "PENDING",
          },
        ],
      }),
    );
    expect(chip.detail).not.toBe("—");
    expect(chip.detail).not.toBe("unavailable");
    expect(chip.detail.toLowerCase()).toMatch(/expires|completed|pending|on file/);
  });

  it("resolves chips when Training payload only has source_course_code aliases", () => {
    const inSixty = new Date();
    inSixty.setHours(0, 0, 0, 0);
    inSixty.setDate(inSixty.getDate() + 60);
    const until = inSixty.toISOString().slice(0, 10);
    const chip = competenceChipStatus(
      "QMS-REF",
      training({
        satisfied: [],
        passed: false,
        tracked_records: [
          {
            source_course_code: "QMS REF",
            course_name: "QMS Recurrent Auditor",
            completion_date: "2025-07-01",
            valid_until: until,
            days_until_expiry: 60,
            verification_status: "PENDING",
            record_status: "PENDING",
          },
        ],
      }),
    );
    expect(chip.detail).not.toBe("—");
    expect(chip.detail).not.toBe("unavailable");
    expect(chip.detail).not.toBe("not recorded");
    expect(chip.detail.toLowerCase()).toMatch(/expires|completed|pending|due|nov|day/);
  });

  it("does not label ADMIN as required when a record is on file", () => {
    const chip = competenceChipStatus(
      "QMS-ADMIN",
      training({
        admin: {
          status: "pending_or_inactive",
          course_code: "QMS-ADMIN",
          record: {
            course_code: "QMS-ADMIN",
            completion_date: "2025-02-01",
            verification_status: "PENDING",
            record_status: "PENDING",
            training_status: "NOT_DONE",
          },
        },
        tracked_records: [
          {
            course_code: "QMS-ADMIN",
            completion_date: "2025-02-01",
            verification_status: "PENDING",
            record_status: "PENDING",
            training_status: "NOT_DONE",
          },
        ],
      }),
    );
    expect(chip.detail.toLowerCase()).not.toContain("required");
    expect(chip.detail.toLowerCase()).toMatch(/completed|pending|on file/);
  });

  it("does not mark the alternate currency course required when INIT already passes", () => {
    const chip = competenceChipStatus(
      "QMS-REF",
      training({
        required: ["QMS-INIT", "QMS-REF"],
        satisfied: ["QMS-INIT"],
        missing: [],
        passed: true,
        currency_passed: true,
        tracked_records: [
          {
            course_code: "QMS-INIT",
            completion_date: "2025-01-15",
            verification_status: "VERIFIED",
            record_status: "READY",
          },
        ],
      }),
    );
    expect(chip.detail.toLowerCase()).not.toContain("required");
    expect(chip.tone).toBe("muted");
    expect(chip.detail.toLowerCase()).toMatch(/not held|not recorded/);
  });

  it("shows completed evidence even when Training policy still emits NOT_DONE", () => {
    const chip = competenceChipStatus(
      "QMS-INIT",
      training({
        required: ["QMS-INIT", "QMS-REF"],
        satisfied: [],
        missing: ["QMS-INIT", "QMS-REF"],
        passed: false,
        tracked_records: [
          {
            course_code: "QMS-INIT",
            completion_date: "2025-03-01",
            verification_status: "PENDING",
            record_status: "PENDING",
            training_status: "NOT_DONE",
          },
        ],
      }),
    );
    expect(chip.detail.toLowerCase()).not.toContain("required · not completed");
    expect(chip.detail.toLowerCase()).toContain("completed");
  });

  it("labels missing eligibility snapshot as unavailable instead of a blank dash", () => {
    const chip = competenceChipStatus("QMS-INIT", undefined);
    expect(chip.detail).toBe("unavailable");
  });

  it("caps authorization expiry to the soonest satisfied course valid_until", () => {
    const training = {
      required: ["QMS-INIT", "QMS-REF"],
      satisfied: ["QMS-INIT", "QMS-REF"],
      missing: [],
      expired: [],
      records: [
        { course_code: "QMS-INIT", valid_until: null },
        { course_code: "QMS-REF", valid_until: "2030-01-15" },
      ],
      expired_records: [],
      tracked_records: [],
      passed: true,
    };
    expect(earliestCompetenceValidUntil(training, new Date("2026-09-21T12:00:00"))).toBe("2030-01-15");
    expect(capPrivilegeExpiresOn(null, training, new Date("2026-09-21T12:00:00"))).toBe("2030-01-15");
    expect(capPrivilegeExpiresOn("2035-01-01", training, new Date("2026-09-21T12:00:00"))).toBe("2030-01-15");
    expect(capPrivilegeExpiresOn("2029-06-01", training, new Date("2026-09-21T12:00:00"))).toBe("2029-06-01");
  });
});
