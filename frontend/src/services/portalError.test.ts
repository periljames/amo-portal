import { describe, expect, it } from "vitest";
import {
  portalErrorMessage,
  portalErrorTitle,
  reportPortalError,
  reportUploadError,
} from "./portalError";

describe("portal error feedback", () => {
  it("keeps useful backend validation details", () => {
    expect(portalErrorMessage({
      detail: [
        { loc: ["body", "file"], msg: "A PDF file is required" },
        { loc: ["body", "file"], msg: "The file exceeds 20 MiB" },
      ],
    })).toBe("A PDF file is required; The file exceeds 20 MiB");
  });

  it("uses action-specific titles instead of a generic hidden error", () => {
    expect(portalErrorTitle("form")).toBe("Review the highlighted information");
    expect(portalErrorTitle("upload")).toBe("Upload failed");
    expect(portalErrorTitle("api")).toBe("Action failed");
  });

  it("makes blocking errors persistent by default", () => {
    const detail = reportPortalError(new Error("The record could not be saved"), {
      source: "api",
      code: "409",
    });
    expect(detail).toMatchObject({
      title: "Action failed",
      message: "The record could not be saved",
      code: "409",
      persistent: true,
    });
  });

  it("gives uploads a useful fallback message", () => {
    const detail = reportUploadError(null);
    expect(detail.title).toBe("Upload failed");
    expect(detail.message).toContain("format and size");
    expect(detail.persistent).toBe(true);
  });
});
