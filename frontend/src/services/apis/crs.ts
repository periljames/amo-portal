// src/services/apis/crs.ts
// Compatibility wrapper for older imports that used src/services/apis/*
// Uses the real HTTP helpers from src/services/crs.ts

import { apiPost } from "../crs";
import { authHeaders } from "../auth";
import type { CRSCreate, CRSRead } from "../../types/crs";

export async function createCRS(payload: CRSCreate): Promise<CRSRead> {
  return apiPost<CRSRead>("/crs/", payload, {
    headers: authHeaders(),
  });
}
