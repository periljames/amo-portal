// src/services/qmsInbox.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsInboxResponse } from "../types/qms";

export function getQmsInbox(amoCode: string): Promise<QmsInboxResponse> {
  return apiRequest<QmsInboxResponse>(qmsPath(amoCode, "/inbox"));
}
