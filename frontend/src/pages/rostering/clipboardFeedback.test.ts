/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const feedbackSource = readSource("../../clipboardFeedback.ts");
const feedbackCss = readSource("../../styles/components/clipboard-feedback.css");
const indexSource = readSource("../../../index.html");

describe("global clipboard feedback", () => {
  it("loads before the application and wraps successful clipboard writes", () => {
    expect(indexSource).toContain('/src/clipboardFeedback.ts');
    expect(indexSource.indexOf('/src/clipboardFeedback.ts')).toBeLessThan(
      indexSource.indexOf('/src/main.tsx'),
    );
    expect(feedbackSource).toContain("navigator.clipboard");
    expect(feedbackSource).toContain("boundWriteText(text)");
    expect(feedbackSource).toContain('markTrigger(trigger, "success")');
    expect(feedbackSource).toContain('announceFeedback("success")');
  });

  it("provides visible and accessible success and failure confirmation", () => {
    expect(feedbackSource).toContain('setAttribute("role", "status")');
    expect(feedbackSource).toContain('setAttribute("aria-live", "polite")');
    expect(feedbackSource).toContain('setAttribute("aria-atomic", "true")');
    expect(feedbackSource).toContain("Content copied successfully");
    expect(feedbackSource).toContain("Copy failed. Please try again.");
    expect(feedbackSource).toContain('markTrigger(trigger, "error")');
    expect(feedbackSource).toContain("2400");
  });

  it("animates the clicked trigger and respects reduced motion", () => {
    expect(feedbackCss).toContain('[data-copy-feedback="success"]');
    expect(feedbackCss).toContain('content: "Copied"');
    expect(feedbackCss).toContain("amo-clipboard-toast-in");
    expect(feedbackCss).toContain("amo-clipboard-check-pop");
    expect(feedbackCss).toContain("amo-copy-trigger-confirm");
    expect(feedbackCss).toContain("prefers-reduced-motion: reduce");
  });
});
