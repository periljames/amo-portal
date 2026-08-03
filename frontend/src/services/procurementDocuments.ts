import { apiRequest } from "./apiClient";
import type { ProcurementEvidence } from "../types/procurementDocuments";

function base(amoCode: string): string {
  return `/api/maintenance/${encodeURIComponent(amoCode)}/procurement`;
}

function json<T>(method: string, body?: unknown): RequestInit {
  return {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  };
}

export function listProcurementDocuments(amoCode: string): Promise<ProcurementEvidence[]> {
  return apiRequest<ProcurementEvidence[]>(`${base(amoCode)}/documents`, { cacheTtlMs: 0 });
}

export function uploadProcurementDocument(
  amoCode: string,
  payload: {
    entityType: string;
    entityId: string;
    documentKind: string;
    title: string;
    notes?: string;
    file: File;
  },
): Promise<ProcurementEvidence> {
  const body = new FormData();
  body.append("entity_type", payload.entityType);
  body.append("entity_id", payload.entityId);
  body.append("document_kind", payload.documentKind);
  body.append("title", payload.title);
  if (payload.notes) body.append("notes", payload.notes);
  body.append("file", payload.file);
  return apiRequest<ProcurementEvidence>(`${base(amoCode)}/documents/upload`, {
    method: "POST",
    body,
    timeoutMs: 120000,
  });
}

export function linkProcurementDocument(amoCode: string, payload: Record<string, unknown>): Promise<ProcurementEvidence> {
  return apiRequest<ProcurementEvidence>(`${base(amoCode)}/documents/link`, json("POST", payload));
}

export function verifyProcurementDocument(
  amoCode: string,
  documentId: number,
  verified = true,
  note?: string,
): Promise<ProcurementEvidence> {
  return apiRequest<ProcurementEvidence>(
    `${base(amoCode)}/documents/${documentId}/verify`,
    json("POST", { verified, note }),
  );
}
