import { apiJson, jsonBody } from "./typedApi";

export type RosterAircraftAllocationType =
  | "FLIGHT_ENGINEERING"
  | "MAINTENANCE_SUPPORT"
  | "OTHER";

export type RosterAircraftAllocationRead = {
  id: string;
  roster_assignment_id: string;
  aircraft_serial_number: string;
  aircraft_registration: string;
  aircraft_display_code: string;
  starts_at: string;
  ends_at: string;
  allocation_type: RosterAircraftAllocationType;
  notes: string | null;
  can_delete: boolean;
};

export type RosterAircraftAllocationCreate = {
  aircraft_serial_number: string;
  starts_at?: string | null;
  ends_at?: string | null;
  allocation_type?: RosterAircraftAllocationType;
  notes?: string | null;
};

export function listRosterAircraftAllocations(
  assignmentId: string,
): Promise<RosterAircraftAllocationRead[]> {
  return apiJson(
    `/rostering/assignments/${encodeURIComponent(assignmentId)}/aircraft-allocations`,
    { offline: { cacheTtlMs: 45_000 } },
  );
}

export function createRosterAircraftAllocation(
  assignmentId: string,
  payload: RosterAircraftAllocationCreate,
): Promise<RosterAircraftAllocationRead> {
  return apiJson(
    `/rostering/assignments/${encodeURIComponent(assignmentId)}/aircraft-allocations`,
    { method: "POST", body: jsonBody(payload) },
  );
}

export function deleteRosterAircraftAllocation(
  assignmentId: string,
  allocationId: string,
): Promise<void> {
  return apiJson(
    `/rostering/assignments/${encodeURIComponent(assignmentId)}/aircraft-allocations/${encodeURIComponent(allocationId)}`,
    { method: "DELETE" },
  );
}
