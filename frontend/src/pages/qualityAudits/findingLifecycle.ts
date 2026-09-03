import type { CAROut, QMSFindingOut } from "../../services/qms";

/**
 * Operational finding+CAR lifecycle filters.
 *
 * Backend `workflow_stage` values are preserved for the paged register API.
 * Live fieldwork that auto-creates OPEN CARs lands in `with_auditee` ("Awaiting response"),
 * not `needs_review` ("RCA/CAP"). Default register view is `all` so those rows stay discoverable.
 */
export type FindingLifecycleView =
  | "all"
  | "needs_review"
  | "with_auditee"
  | "implementation"
  | "effectiveness"
  | "closed";

/** Stages that map 1:1 to the register `workflow_stage` query param. */
export type FindingWorkflowStage = Exclude<FindingLifecycleView, "all">;

export const FINDING_LIFECYCLE_OPTIONS: Array<{ value: FindingLifecycleView; label: string }> = [
  { value: "all", label: "All" },
  { value: "with_auditee", label: "Awaiting response" },
  { value: "needs_review", label: "RCA/CAP" },
  { value: "implementation", label: "Implementation" },
  { value: "effectiveness", label: "Effectiveness" },
  { value: "closed", label: "Closed" },
];

export const DEFAULT_FINDING_LIFECYCLE: FindingLifecycleView = "all";

export function parseFindingLifecycleView(raw: string | null | undefined): FindingLifecycleView {
  if (!raw) return DEFAULT_FINDING_LIFECYCLE;
  return FINDING_LIFECYCLE_OPTIONS.some((option) => option.value === raw)
    ? (raw as FindingLifecycleView)
    : DEFAULT_FINDING_LIFECYCLE;
}

export function toRegisterWorkflowStage(stage: FindingLifecycleView): FindingWorkflowStage | undefined {
  return stage === "all" ? undefined : stage;
}

export function primaryLinkedCar(cars: CAROut[]): CAROut | null {
  return cars.find((car) => !["CLOSED", "CANCELLED"].includes(car.status)) ?? cars[0] ?? null;
}

export function findingLifecycleView(finding: QMSFindingOut, cars: CAROut[]): FindingWorkflowStage {
  if (finding.closed_at) return "closed";
  const car = primaryLinkedCar(cars);
  if (!car || car.status === "DRAFT") return "needs_review";
  if (car.status === "CLOSED") return "closed";
  if (car.status === "PENDING_VERIFICATION") return "effectiveness";
  if (car.status === "IN_PROGRESS") return "implementation";
  return "with_auditee";
}

export function findingLifecycleLabel(stage: FindingLifecycleView | FindingWorkflowStage): string {
  return FINDING_LIFECYCLE_OPTIONS.find((option) => option.value === stage)?.label ?? stage;
}

export function findingNextAction(stage: FindingLifecycleView | FindingWorkflowStage, hasLinkedCar: boolean): string {
  if (!hasLinkedCar) return "Create corrective action";
  if (stage === "closed") return "Review closed corrective action";
  if (stage === "effectiveness") return "Complete effectiveness review";
  if (stage === "implementation") return "Continue implementation";
  if (stage === "with_auditee") return "Continue auditee response";
  if (stage === "needs_review") return "Continue RCA / CAP";
  return "Review corrective action";
}
