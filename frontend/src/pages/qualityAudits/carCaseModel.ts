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
export function carAging(car: CAROut, now = new Date()) {
  const day = (value: string) => Date.parse(`${value.slice(0,10)}T00:00:00Z`);
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const terminal = ['CLOSED','CANCELLED'].includes(car.status);
  const due = car.due_date || car.target_closure_date;
  const days = due ? Math.round((day(due)-today)/86400000) : NaN;
  const issued = car.date_issued || car.created_at;
  const end = terminal && (car.date_closed || car.closed_at) ? day((car.date_closed || car.closed_at)!) : today;
  const age = issued ? Math.max(0,Math.floor((end-day(issued))/86400000)) : NaN;
  return { tone: terminal ? 'closed' : days < 0 ? 'overdue' : days <= 7 ? 'soon' : 'normal',
    label: terminal ? (car.status==='CLOSED'?'Closed':'Cancelled') : !Number.isFinite(days) ? 'No deadline' : days < 0 ? `${Math.abs(days)} days overdue` : days === 0 ? 'Due today' : days === 1 ? 'Due tomorrow' : `Due in ${days} days`,
    age: Number.isFinite(age) ? `${age} days ${terminal?'to closure':'open'}` : null };
}
export function caseDate(value?: string | null) {
  if (!value) return "Not set";
  const parsed = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00` : value);
  return Number.isNaN(parsed.getTime()) ? "Not set" : parsed.toLocaleDateString(undefined, {day:"numeric",month:"short",year:"numeric"});
}

