// src/services/apis/crs.ts
import { apiPost } from "../api";
import type { CRSCreate, CRSRead } from "../../types/crs";

export async function createCRS(payload: CRSCreate): Promise<CRSRead> {
  return apiPost<CRSRead>("/crs/", JSON.stringify(payload), {
    headers: {
      "Content-Type": "application/json",
    },
  });
}
