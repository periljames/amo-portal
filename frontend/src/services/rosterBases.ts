import { listBaseStations } from "./foundations";
import type { BaseStationRead } from "../types/foundations";

/** Reuse the tenant-wide Foundations base master inside Rostering. */
export function listRosterBaseStations(includeInactive = false): Promise<BaseStationRead[]> {
  return listBaseStations({ include_inactive: includeInactive });
}
