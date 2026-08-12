import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

export type DocumentEvidenceCategory =
  | "GENERAL"
  | "WORKFLOW"
  | "AUTHORITY"
  | "DISTRIBUTION"
  | "CONTROLLED_COPY"
  | "REVIEW"
  | "EXTERNAL_SOURCE"
  | "CHANGE";

export type DocumentEvidenceAsset = {
  asset_id: string;
  manual_id: string;
  revision_id: string | null;
  category: DocumentEvidenceCategory;
  purpose: string | null;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  description: string | null;
  uploaded_by_user_id: string | null;
  source_context: Record<string, unknown>;
  created_at: string | null;
  download_url: string;
};

export type DocumentEvidenceReference = Pick<
  DocumentEvidenceAsset,
  "asset_id" | "filename" | "mime_type" | "sha256" | "size_bytes" | "category"
>;

export type DocumentEvidencePackDownload = {
  blob: Blob;
  filename: string;
  sha256: string | null;
  attachmentCount: number | null;
};

async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.clone().json();
    const detail = payload?.detail;
    if (typeof detail === "string") return detail;
    if (typeof detail?.message === "string") return detail.message;
  } catch {
    // Preserve the operational fallback.
  }
  return `${fallback} (${response.status}).`;
}

function attachmentFilename(response: Response, fallback: string): string {
  const disposition = response.headers.get("content-disposition") || "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded.replace(/^"|"$/g, ""));
    } catch {
      return encoded.replace(/^"|"$/g, "");
    }
  }
  return disposition.match(/filename="([^"]+)"/i)?.[1] || fallback;
}

export async function listDocumentEvidenceAssets(
  tenant: string,
  manualId: string,
  revisionId?: string | null,
): Promise<DocumentEvidenceAsset[]> {
  const query = new URLSearchParams();
  if (revisionId) query.set("revision_id", revisionId);
  const suffix = query.size ? `?${query.toString()}` : "";
  const response = await fetch(
    `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/documents/${encodeURIComponent(manualId)}/evidence-assets${suffix}`,
    { headers: authHeaders(), credentials: "same-origin" },
  );
  if (!response.ok) throw new Error(await errorMessage(response, "Document evidence could not be loaded"));
  const payload = await response.json();
  return Array.isArray(payload?.items) ? payload.items as DocumentEvidenceAsset[] : [];
}

export async function uploadDocumentEvidenceAsset(
  tenant: string,
  manualId: string,
  input: {
    file: File;
    revisionId?: string | null;
    category?: DocumentEvidenceCategory;
    purpose?: string;
    description?: string;
  },
): Promise<DocumentEvidenceAsset> {
  const form = new FormData();
  form.set("artifact", input.file);
  if (input.revisionId) form.set("revision_id", input.revisionId);
  form.set("category", input.category || "GENERAL");
  if (input.purpose?.trim()) form.set("purpose", input.purpose.trim());
  if (input.description?.trim()) form.set("description", input.description.trim());
  const response = await fetch(
    `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/documents/${encodeURIComponent(manualId)}/evidence-assets`,
    {
      method: "POST",
      headers: authHeaders(),
      credentials: "same-origin",
      body: form,
    },
  );
  if (!response.ok) throw new Error(await errorMessage(response, "Evidence could not be retained"));
  return response.json() as Promise<DocumentEvidenceAsset>;
}

export async function downloadDocumentEvidenceAsset(asset: DocumentEvidenceAsset): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${asset.download_url}`, {
    headers: authHeaders(),
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error(await errorMessage(response, "Evidence file could not be downloaded"));
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = asset.filename;
  anchor.click();
  URL.revokeObjectURL(href);
}

export async function downloadDocumentEvidencePack(
  tenant: string,
  manualId: string,
  revisionId?: string | null,
): Promise<DocumentEvidencePackDownload> {
  const query = new URLSearchParams();
  if (revisionId) query.set("revision_id", revisionId);
  const suffix = query.size ? `?${query.toString()}` : "";
  const response = await fetch(
    `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/documents/${encodeURIComponent(manualId)}/evidence-pack.zip${suffix}`,
    { headers: authHeaders(), credentials: "same-origin" },
  );
  if (!response.ok) throw new Error(await errorMessage(response, "Document evidence pack could not be generated"));
  const attachmentHeader = response.headers.get("x-evidence-pack-attachments");
  const parsedAttachments = attachmentHeader === null ? Number.NaN : Number.parseInt(attachmentHeader, 10);
  return {
    blob: await response.blob(),
    filename: attachmentFilename(response, "document-evidence-pack.zip"),
    sha256: response.headers.get("x-evidence-pack-sha256"),
    attachmentCount: Number.isFinite(parsedAttachments) ? parsedAttachments : null,
  };
}

export function saveDocumentEvidencePack(result: DocumentEvidencePackDownload): void {
  const href = URL.createObjectURL(result.blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = result.filename;
  anchor.click();
  URL.revokeObjectURL(href);
}

export function evidenceReference(asset: DocumentEvidenceAsset): DocumentEvidenceReference {
  return {
    asset_id: asset.asset_id,
    filename: asset.filename,
    mime_type: asset.mime_type,
    sha256: asset.sha256,
    size_bytes: asset.size_bytes,
    category: asset.category,
  };
}
