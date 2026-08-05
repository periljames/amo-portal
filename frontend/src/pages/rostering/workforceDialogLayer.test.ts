import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const dialogCss = readFileSync(
  new URL("../../styles/workforce-dialog-layer.css", import.meta.url),
  "utf8",
);

describe("Workforce dialog layer", () => {
  it("keeps the scrim behind the contract editor instead of blurring the form", () => {
    expect(dialogCss).toContain("body:has(.hr-decision)::before");
    expect(dialogCss).toContain("content: none");
    expect(dialogCss).not.toContain("backdrop-filter");
    expect(dialogCss).toContain("0 0 0 100vmax");
    expect(dialogCss).toContain("pointer-events: none");
    expect(dialogCss).toContain("pointer-events: auto");
  });

  it("locks page scrolling while preserving the sticky contract actions", () => {
    expect(dialogCss).toContain("body:has(.hr-decision)");
    expect(dialogCss).toContain("overflow: hidden");
    expect(dialogCss).toContain(".hr-contract-editor .wr-actions--end");
    expect(dialogCss).toContain("position: sticky");
  });
});
