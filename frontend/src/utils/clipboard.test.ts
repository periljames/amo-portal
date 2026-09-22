import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { copyTextToClipboard } from "./clipboard";

describe("copyTextToClipboard", () => {
  const originalClipboard = navigator.clipboard;
  const originalDocument = globalThis.document;

  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: vi.fn(async () => undefined),
      },
    });
  });

  afterEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: originalClipboard,
    });
    if (originalDocument === undefined) {
      // @ts-expect-error restore missing document in node
      delete globalThis.document;
    } else {
      globalThis.document = originalDocument;
    }
  });

  it("copies via the clipboard API when available", async () => {
    await expect(copyTextToClipboard("ID-ABC12345")).resolves.toBe(true);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("ID-ABC12345");
  });

  it("falls back to execCommand when clipboard write fails", async () => {
    (navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("denied"));
    const area = {
      value: "",
      setAttribute: vi.fn(),
      style: {} as CSSStyleDeclaration,
      select: vi.fn(),
      setSelectionRange: vi.fn(),
    };
    const fakeDocument = {
      createElement: vi.fn(() => area),
      body: {
        appendChild: vi.fn(),
        removeChild: vi.fn(),
      },
      execCommand: vi.fn(() => true),
    };
    // @ts-expect-error test double
    globalThis.document = fakeDocument;
    await expect(copyTextToClipboard("ISSUE_CODE")).resolves.toBe(true);
    expect(fakeDocument.execCommand).toHaveBeenCalledWith("copy");
    expect(fakeDocument.body.appendChild).toHaveBeenCalled();
    expect(fakeDocument.body.removeChild).toHaveBeenCalled();
  });

  it("rejects empty values", async () => {
    await expect(copyTextToClipboard("")).resolves.toBe(false);
    expect(navigator.clipboard.writeText).not.toHaveBeenCalled();
  });
});
