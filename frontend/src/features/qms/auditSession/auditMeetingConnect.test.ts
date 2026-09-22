import { describe, expect, it } from "vitest";

import {
  auditMeetingSubject,
  isTeamsMeetingUrl,
  teamsCreateMeetingUrl,
} from "./auditMeetingConnect";

describe("auditMeetingConnect", () => {
  it("builds a Teams new-meeting deep link", () => {
    const url = teamsCreateMeetingUrl({
      subject: "Opening meeting · QAR/MO/26/004",
      start: "2026-09-25T08:00",
      end: "2026-09-25T09:00",
    });
    expect(url.startsWith("https://teams.microsoft.com/l/meeting/new?")).toBe(true);
    expect(url).toContain("subject=");
    expect(url).toContain("startTime=2026-09-25T08%3A00%3A00");
    expect(url).toContain("endTime=2026-09-25T09%3A00%3A00");
  });

  it("recognizes Teams join URLs", () => {
    expect(isTeamsMeetingUrl("https://teams.microsoft.com/l/meetup-join/19%3ameeting")).toBe(true);
    expect(isTeamsMeetingUrl("https://example.com/meet")).toBe(false);
  });

  it("names meetings from audit identity", () => {
    expect(
      auditMeetingSubject("OPENING", "test audit", "QAR/MO/26/004"),
    ).toBe("Opening meeting · QAR/MO/26/004 · test audit");
  });
});
