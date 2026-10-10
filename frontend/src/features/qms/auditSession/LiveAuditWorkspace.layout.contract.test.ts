import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const live = readFileSync(new URL("./LiveAuditWorkspace.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../../../styles/qms-live-audit-workspace.css", import.meta.url), "utf8");

describe("auditor-first Fieldwork workspace", () => {
  it("puts response, notes, evidence and actions ahead of optional compliance detail", () => {
    const positions = [
      'className="qms-live-audit-focus__entry"',
      'className="qms-live-audit-focus__responses"',
      '<LiveAuditEvidenceStrip',
      'className="qms-live-audit-focus__nav"',
      'className="qms-live-audit-focus__source-details"',
      'className="qms-live-audit-focus__compliance"',
    ].map((marker) => live.indexOf(marker));
    expect(positions.every((position) => position >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
    // The old dashboard below the reordered panel must not reappear as a duplicate editor.
    expect(live.match(/className="qms-live-audit-focus__responses"/g)).toHaveLength(1);
    expect(live.match(/<LiveAuditEvidenceStrip/g)).toHaveLength(1);
    expect(live.match(/className="qms-live-audit-focus__nav"/g)).toHaveLength(1);
  });

  it("only advances Save & next after a confirmed checklist mutation", () => {
    const start = live.indexOf("const saveAndNext = async () => {");
    const end = live.indexOf("const selectResponse =", start);
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const handler = live.slice(start, end);
    expect(handler).toContain("await updateMutation.mutateAsync");
    expect(handler.indexOf("await updateMutation.mutateAsync")).toBeLessThan(handler.indexOf("selectItem(nextItemId)"));
    expect(handler).toContain("evidenceCapture.hasDraft");
    expect(handler).toContain("catch {");
  });

  it("preserves governed execution, controlled source, finding and offline safeguards", () => {
    for (const marker of [
      "createAtomicChecklistFinding",
      "assessmentIntegrityError",
      "N/A requires an explicit governed applicability basis",
      "applicability_recommendation",
      "documentary_recommendation",
      "Current-approved documentary candidates",
      "Competing controlled statements",
      "LiveAuditEvidenceStrip",
      "isOfflineQueuedError",
      "FIELDWORK_VERSION_CONFLICT",
      "unsavedDraftCount",
      "completionBlockers",
      "canExecuteAssignedAudit",
      "canCompleteAuditFieldwork",
      "Released-data boundary active",
    ]) {
      expect(live).toContain(marker);
    }
  });

  it("supports stable item numbering, mobile question access and visible unsaved drafts", () => {
    expect(live).toContain("itemNumberById");
    expect(live).toContain('value="VERIFIED"');
    expect(live).toContain("dirtyItemIds.has(item.checklist_item_id)");
    expect(live).toContain('aria-controls="audit-occurrence-checklist"');
    expect(live).toContain("is-navigation-open");
    expect(live).toContain("Frozen checklist question differs from the execution question");
    expect(styles).toContain(".qms-live-audit-focus__body.is-navigation-open .qms-live-audit-focus__sections");
    expect(styles).toContain(":focus-visible");
  });
});
