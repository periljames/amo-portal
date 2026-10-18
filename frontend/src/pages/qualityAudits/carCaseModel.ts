import type { CAROut } from "../../services/qms";

export function carNextAction(car: CAROut): string {
  if (car.status === "CLOSED") return "Closed";
  if (car.status === "CANCELLED") return "Cancelled";
  if (car.status === "ESCALATED") return "Executive review";
  if ([car.root_cause_status, car.capa_status].includes("SUBMITTED")) return "Quality review";
  if ([car.root_cause_status, car.capa_status].some(s => s === "REJECTED" || s === "NEEDS_EVIDENCE")) return "Auditee revision";
  if (car.status === "PENDING_VERIFICATION") return "Effectiveness review";
  if (!car.submitted_at) return "Auditee response";
  return "Implementation";
}
export const carHasReview = (car: CAROut) => car.status === "PENDING_VERIFICATION" && [car.root_cause_status, car.capa_status].includes("SUBMITTED");
export function caseDate(value?: string | null) {
  if (!value) return "Not set";
  const parsed = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00` : value);
  return Number.isNaN(parsed.getTime()) ? "Not set" : parsed.toLocaleDateString(undefined, {day:"numeric",month:"short",year:"numeric"});
}

