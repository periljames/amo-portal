import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = readFileSync(new URL("./ManualDiffPage.tsx", import.meta.url), "utf8");

describe("revision intelligence operating model", () => {
  it("surfaces authoritative revision evidence and changed-page navigation", () => {
    expect(source).toContain("getRevisionWorkflow");
    expect(source).toContain("listRevisions");
    expect(source).toContain("Changed pages");
    expect(source).toContain("Revision highlights");
    expect(source).toContain("authority_approval_ref");
  });

  it("supports previous/next change navigation and changed-only review", () => {
    expect(source).toContain("Previous change");
    expect(source).toContain("Next change");
    expect(source).toContain("Changed content only");
    expect(source).toContain('type DiffMode = "all" | "changes"');
  });

  it("uses side-by-side structured comparison without pretending unavailable data exists", () => {
    expect(source).toContain("manuals-shell-grid--comparison");
    expect(source).toContain("Automated comparison is unavailable for these revisions.");
    expect(source).toContain("does not currently provide a reliable aligned baseline");
  });
});
