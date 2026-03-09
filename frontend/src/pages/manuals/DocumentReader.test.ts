import { describe, expect, it } from "vitest";
import { buildFallbackSections, filteredSectionRange } from "./DocumentReader";

describe("DocumentReader section helpers", () => {
  it("builds fallback sections with stable ids", () => {
    const sections = buildFallbackSections(
      [
        { id: "a", heading: "1.0 General", level: 1 },
        { id: "b", heading: "1.1 Scope", level: 2 },
      ],
      [
        { section_id: "a", html: "<p>A</p>" },
        { section_id: "b", html: "<p>B</p>" },
      ],
    );
    expect(sections).toHaveLength(2);
    expect(sections[0].id).toContain("1-0-general");
  });

  it("creates virtualized window around active section", () => {
    const sections = Array.from({ length: 20 }, (_, i) => ({ id: `s-${i}`, label: `Section ${i}`, level: 1 as const, html: "" }));
    const range = filteredSectionRange(sections, "s-10");
    expect(range.start).toBe(7);
    expect(range.end).toBe(14);
  });
});
