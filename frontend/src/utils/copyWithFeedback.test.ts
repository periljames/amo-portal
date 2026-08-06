import { afterEach, describe, expect, it, vi } from "vitest";

import { copyWithFeedback, type CopyFeedbackState } from "./copyWithFeedback";

describe("copyWithFeedback", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reports success after the intended clipboard write completes", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const states: CopyFeedbackState[] = [];

    await copyWithFeedback("calendar-link", (state) => states.push(state));

    expect(writeText).toHaveBeenCalledOnce();
    expect(writeText).toHaveBeenCalledWith("calendar-link");
    expect(states).toEqual(["success"]);
  });

  it("reports failure and preserves the clipboard rejection", async () => {
    const failure = new DOMException("Denied", "NotAllowedError");
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(failure) },
    });
    const states: CopyFeedbackState[] = [];

    await expect(copyWithFeedback("calendar-link", (state) => states.push(state))).rejects.toBe(failure);
    expect(states).toEqual(["error"]);
  });
});
