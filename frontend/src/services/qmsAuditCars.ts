import { apiRequest, qmsPath } from "./apiClient";
import { requireAuditContract } from "./qmsAuditWorkflowContract";

export type AuditCar = {
  id: string;
  car_number: string;
  title: string;
  summary: string;
  status: string;
  priority: string;
  due_date: string | null;
  target_closure_date: string | null;
  closed_at: string | null;
  escalated_at: string | null;
  assigned_to_user_id: string | null;
  finding_id: string | null;
  audit_id?: string | null;
  finding_ref?: string | null;
  days_out?: number | null;
  days_remaining_past?: number | null;
};

type AuditCarRegister = { items: AuditCar[]; total: number; limit: number; offset: number };

/** Both Closing and Follow-up must see every CAR belonging to the occurrence. */
export async function listAuditCorrectiveActions(amoCode: string, auditId: string, signal?: AbortSignal): Promise<AuditCarRegister> {
  const items: AuditCar[] = [];
  const ids = new Set<string>();
  let total: number | null = null;
  for (let pageNumber = 0; pageNumber < 100; pageNumber += 1) {
    const offset = items.length;
    const params = new URLSearchParams({ audit_id: auditId, limit: "200", offset: String(offset) });
    const page = requireAuditContract(await apiRequest<AuditCarRegister>(qmsPath(amoCode, `/cars/register?${params}`), {
      timeoutMs: 15_000, cacheTtlMs: 0, signal,
    }), "cars");
    if (page.offset !== offset || (total !== null && page.total !== total)) {
      throw new Error("The corrective-action register changed while loading. Refresh to load all current audit CARs.");
    }
    total = page.total;
    for (const car of page.items) {
      if (ids.has(car.id) || (car.audit_id && car.audit_id !== auditId)) {
        throw new Error("Corrective actions could not be verified for this audit. Refresh the audit register.");
      }
      ids.add(car.id);
      items.push(car);
    }
    if (items.length === total) return { items, total, limit: items.length || page.limit, offset: 0 };
    if (!page.items.length || items.length > total) break;
  }
  throw new Error("The full corrective-action register could not be loaded. Refresh before making a closure decision.");
}
