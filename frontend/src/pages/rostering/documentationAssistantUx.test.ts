import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const assistant = readFileSync(new URL("../manuals/DocumentationAssistantPanel.tsx", import.meta.url), "utf8");
const assistantCss = readFileSync(new URL("../manuals/documentationAssistantPanel.css", import.meta.url), "utf8");
const workforceCss = readFileSync(new URL("./components/workforce-hr-workspace.css", import.meta.url), "utf8");

describe("documentation assistant interaction contract", () => {
  it("supports persisted pointer and keyboard resizing", () => {
    expect(assistant).toContain("amo_documentation_assistant_width");
    expect(assistant).toContain("if (!storedValue) return clampAssistantWidth(FLOATING_DEFAULT_WIDTH");
    expect(assistant).toContain("onPointerDown={startResize}");
    expect(assistant).toContain("onKeyDown={resizeWithKeyboard}");
    expect(assistant).toContain("onDoubleClick={resetWidth}");
    expect(assistant).toContain("role=\"separator\"");
    expect(assistant).toContain("documentation-assistant__resize-grip");
    expect(assistant).not.toContain("GripVertical");
    expect(assistantCss).toContain("--documentation-assistant-width");
    expect(assistantCss).toContain("cursor: col-resize");
    expect(assistantCss).toContain("prefers-reduced-motion");
  });

  it("keeps the Workforce register bounded, legible and responsive", () => {
    expect(workforceCss).toContain("width: min(100%, 1480px)");
    expect(workforceCss).toContain("var(--text-secondary, #475569)");
    expect(workforceCss).toContain("@media (max-width: 1180px)");
    expect(workforceCss).toContain("grid-template-columns: repeat(2, minmax(0, 1fr))");
  });
});
