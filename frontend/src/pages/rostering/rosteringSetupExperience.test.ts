/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const quickActionsSource = readFileSync(
  new URL("./components/RosterPeriodQuickActions.tsx", import.meta.url),
  "utf8",
);
const ruleEditorSource = readFileSync(
  new URL("./components/RosterRuleQuickEditor.tsx", import.meta.url),
  "utf8",
);
const governanceSource = readFileSync(
  new URL("./components/RosterGovernancePanel.tsx", import.meta.url),
  "utf8",
);
const setupPageSource = readFileSync(
  new URL("./WorkforceRosteringPagesV2.tsx", import.meta.url),
  "utf8",
);
const depthSource = readFileSync(
  new URL("../../styles/theme-depth.css", import.meta.url),
  "utf8",
);

describe("rostering setup experience", () => {
  it("supports fast period creation and audited period modification", () => {
    expect(quickActionsSource).toContain("createRosterPeriod");
    expect(quickActionsSource).toContain("updateRosterPeriod");
    expect(quickActionsSource).toContain("createRosterVersion");
    expect(quickActionsSource).toContain("Edit period");
    expect(quickActionsSource).toContain("New period");
  });

  it("detects the browser timezone and exposes a manual timezone selector", () => {
    expect(quickActionsSource).toContain("Intl.DateTimeFormat().resolvedOptions().timeZone");
    expect(quickActionsSource).toContain("supportedValuesOf?.(\"timeZone\")");
    expect(quickActionsSource).toContain("<select value={draft.timezone_name}");
    expect(quickActionsSource).toContain("detected");
  });

  it("lets authorised administrators change active rule values without exposing them to everyone", () => {
    expect(ruleEditorSource).toContain("roster.manage_rules");
    expect(ruleEditorSource).toContain("updateRosterRule");
    expect(ruleEditorSource).toContain("Save rule");
    expect(ruleEditorSource).toContain("<details");
  });

  it("does not repeat every rule severity in the approval workspace", () => {
    expect(governanceSource).toContain("wr-policy-compact");
    expect(governanceSource).toContain("active checks");
    expect(governanceSource).toContain("hard stops");
    expect(governanceSource).not.toContain("wr-compliance-rule-grid");
    expect(governanceSource).not.toContain("controlled override");
  });

  it("uses concise setup copy while preserving the required lazy settings chunk", () => {
    expect(setupPageSource).toContain("LazyRosterPeriodQuickActions");
    expect(setupPageSource).toContain("LazyRosterRuleQuickEditor");
    expect(setupPageSource).toContain("LazyUnifiedRosterSettings");
    expect(setupPageSource).toContain('eyebrow="Setup"');
    expect(setupPageSource).toContain('description="Periods, shifts, work patterns, contracts, rules and approvals."');
    expect(setupPageSource).not.toContain("Source-aware");
  });

  it("adds portal-wide dark surface separation without changing status colours", () => {
    expect(depthSource).toContain("--surface-elevated: rgba(19, 34, 55, 0.97)");
    expect(depthSource).toContain(".wr-panel");
    expect(depthSource).toContain(".qms-panel");
    expect(depthSource).toContain(".admin-panel");
    expect(depthSource).toContain("inset 0 1px 0");
    expect(depthSource).not.toContain("wr-pill--blocker");
  });
});
