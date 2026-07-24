import { listBaseStations } from "./foundations";
import type { BaseStationRead } from "../types/foundations";

export function listRosterBaseStations(includeInactive = false): Promise<BaseStationRead[]> {
  return listBaseStations({ include_inactive: includeInactive });
}
