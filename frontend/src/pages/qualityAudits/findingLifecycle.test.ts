import { describe, expect, it } from "vitest";
import type { CAROut, QMSFindingOut } from "../../services/qms";
import {
  DEFAULT_FINDING_LIFECYCLE,
  findingLifecycleLabel,
  findingLifecycleView,
  findingNextAction,
  parseFindingLifecycleView,
  toRegisterWorkflowStage,
} from "./findingLifecycle";

const finding = { id: "f-1", closed_at: null } as QMSFindingOut;
const car = (status: CAROut["status"]) => ({ id: `car-${status}`, status } as CAROut);

describe("finding lifecycle projection", () => {
  it("defaults the register to All so Live-raised OPEN CARs stay visible", () => {
    expect(DEFAULT_FINDING_LIFECYCLE).toBe("all");
    expect(parseFindingLifecycleView(null)).toBe("all");
    expect(parseFindingLifecycleView("with_auditee")).toBe("with_auditee");
    expect(toRegisterWorkflowStage("all")).toBeUndefined();
    expect(toRegisterWorkflowStage("with_auditee")).toBe("with_auditee");
  });

  it("keeps unlinked findings in RCA/CAP (needs_review)", () => {
    expect(findingLifecycleView(finding, [])).toBe("needs_review");
    expect(findingLifecycleLabel("needs_review")).toBe("Quality review");
    expect(findingNextAction("needs_review", false)).toBe("Review finding and corrective action requirement");
  });

  it.each([
    ["OPEN", "with_auditee", "Awaiting response"],
    ["ESCALATED", "with_auditee", "Awaiting response"],
    ["IN_PROGRESS", "implementation", "Implementation"],
    ["PENDING_VERIFICATION", "effectiveness", "Effectiveness"],
    ["CLOSED", "effectiveness", "Effectiveness"],
  ] as const)("maps %s corrective actions to %s (%s)", (status, expected, label) => {
    expect(findingLifecycleView(finding, [car(status)])).toBe(expected);
    expect(findingLifecycleLabel(expected)).toBe(label);
  });

  it("treats a closed finding as closed regardless of CAR state", () => {
    expect(findingLifecycleView({ ...finding, closed_at: "2026-08-25T00:00:00Z" }, [car("OPEN")])).toBe("closed");
  });

  it("puts a submitted response in Quality review before effectiveness", () => {
    expect(findingLifecycleView(finding, [{...car("PENDING_VERIFICATION"), root_cause_status:"SUBMITTED",capa_status:"SUBMITTED"}])).toBe("needs_review");
    expect(findingLifecycleView(finding, [{...car("IN_PROGRESS"),capa_status:"NEEDS_EVIDENCE"}])).toBe("with_auditee");
  });

  it("documents that OPEN CARs are not Needs review / RCA/CAP", () => {
    expect(findingLifecycleView(finding, [car("OPEN")])).not.toBe("needs_review");
    expect(findingLifecycleView(finding, [car("OPEN")])).toBe("with_auditee");
  });
});

it("keeps an observation out of corrective-action queues", () => {
 const observation = { ...finding, finding_type: "OBSERVATION", level: "LEVEL_4" } as QMSFindingOut;
 expect(findingLifecycleView(observation, [])).toBe("observation");
 expect(findingNextAction("observation", false)).toBe("Review observation and supporting evidence");
 expect(findingLifecycleView({ ...observation, closed_at: "2026-10-18T00:00:00Z" }, [])).toBe("closed");
});
