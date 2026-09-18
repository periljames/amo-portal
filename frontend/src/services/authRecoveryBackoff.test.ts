import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthRecoveryBackoff } from "./authRecoveryBackoff";

afterEach(() => vi.restoreAllMocks());

describe("authentication recovery retry policy", () => {
  it("honours Retry-After seconds and adds only positive jitter", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    const backoff = new AuthRecoveryBackoff();
    expect(backoff.defer(new Response(null, { status: 429, headers: { "Retry-After": "60" } }), 1000))
      .toBe(61500);
  });

  it("honours HTTP dates and backs off malformed headers", () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    const now = Date.parse("2026-09-16T12:00:00Z");
    const backoff = new AuthRecoveryBackoff();
    expect(backoff.defer(new Response(null, { headers: { "Retry-After": "Wed, 16 Sep 2026 12:01:00 GMT" } }), now))
      .toBe(now + 60000);
    expect(backoff.defer(new Response(null, { headers: { "Retry-After": "invalid" } }), now))
      .toBe(now + 4000);
  });

  it("caps exponential transport backoff and resets on success", () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    const backoff = new AuthRecoveryBackoff();
    expect(backoff.defer(undefined, 1000)).toBe(3000);
    for (let i = 0; i < 100; i++) backoff.defer(undefined, 1000);
    expect(backoff.retryAt).toBe(61000);
    backoff.reset();
    expect(backoff.retryAt).toBe(0);
    expect(backoff.defer(undefined, 1000)).toBe(3000);
  });
});
