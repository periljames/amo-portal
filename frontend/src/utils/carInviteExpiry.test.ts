import { afterEach, describe, expect, it } from "vitest";
import { formatInviteExpiryLocal, parseInviteExpiryLocal } from "./carInviteExpiry";

const initialTimezone = process.env.TZ;
afterEach(() => {
  if (initialTimezone === undefined) delete process.env.TZ;
  else process.env.TZ = initialTimezone;
});

describe("CAR invitation expiry local-time controls", () => {
  it("roundtrips unchanged expiry in Nairobi without shortening bearer access", () => {
    process.env.TZ = "Africa/Nairobi";
    const original = "2026-11-01T12:00:00Z";
    const displayed = formatInviteExpiryLocal(original);
    expect(displayed).toBe("2026-11-01T15:00");
    expect(parseInviteExpiryLocal(displayed, original)).toBe(new Date(original).toISOString());
  });

  it("roundtrips unchanged expiry in a negative UTC offset", () => {
    process.env.TZ = "America/New_York";
    const original = "2026-11-01T12:00:00Z";
    const displayed = formatInviteExpiryLocal(original);
    expect(displayed).toBe("2026-11-01T07:00");
    expect(parseInviteExpiryLocal(displayed, original)).toBe(original);
  });

  it("preserves the original instant in an ambiguous autumn DST fold", () => {
    process.env.TZ = "America/New_York";
    const firstOccurrence = "2026-11-01T05:30:00Z";
    const secondOccurrence = "2026-11-01T06:30:00Z";
    expect(formatInviteExpiryLocal(firstOccurrence)).toBe("2026-11-01T01:30");
    expect(formatInviteExpiryLocal(secondOccurrence)).toBe("2026-11-01T01:30");
    expect(parseInviteExpiryLocal("2026-11-01T01:30", firstOccurrence)).toBe(new Date(firstOccurrence).toISOString());
    expect(parseInviteExpiryLocal("2026-11-01T01:30", secondOccurrence)).toBe(new Date(secondOccurrence).toISOString());
  });

  it("saves an actual changed local deadline and rejects non-existent DST time", () => {
    process.env.TZ = "America/New_York";
    expect(parseInviteExpiryLocal("2026-11-02T10:00", "2026-11-01T12:00:00Z"))
      .toBe("2026-11-02T15:00:00.000Z");
    expect(() => parseInviteExpiryLocal("2026-03-08T02:30", null))
      .toThrow(/valid local date and time/);
    expect(parseInviteExpiryLocal("", "2026-11-01T12:00:00Z")).toBeNull();
  });
});
