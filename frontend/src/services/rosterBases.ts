import { apiJson, queryString } from "./typedApi";
import type { BaseStationRead } from "../types/foundations";

export function listRosterBaseStations(includeInactive = false): Promise<BaseStationRead[]> {
  return apiJson(`/foundations/base-stations${queryString({ include_inactive: includeInactive })}`, {
    offline: { cacheTtlMs: 15 * 60_000 },
  });
}
