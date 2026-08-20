import { describe, expect, it } from "vitest";

import { CLIENT_TIMEZONE_HEADER, detectClientTimeZone } from "./offlineHttp";


describe("portal client timezone context", () => {
  it("uses the browser IANA timezone without geolocation permission", () => {
    const browserZone = String(Intl.DateTimeFormat().resolvedOptions().timeZone || "").trim();
    const detected = detectClientTimeZone();

    expect(CLIENT_TIMEZONE_HEADER).toBe("X-AMO-Client-Timezone");
    expect(detected).toBe(browserZone || null);
  });

  it("returns a timezone identifier accepted by Intl when one is available", () => {
    const detected = detectClientTimeZone();
    if (!detected) return;

    expect(() => new Intl.DateTimeFormat("en", { timeZone: detected }).format(new Date(0))).not.toThrow();
  });
});
