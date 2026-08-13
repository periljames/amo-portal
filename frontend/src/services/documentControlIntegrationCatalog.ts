import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

export type DocumentIntegrationCatalogTable = {
  name: string;
  entity_type: string;
  id_column: string;
  tenant_column: string;
  display_columns: string[];
};

export type DocumentIntegrationCatalogModule = {
  module: string;
  tables: DocumentIntegrationCatalogTable[];
};

export type DocumentIntegrationCatalogResponse = {
  modules: DocumentIntegrationCatalogModule[];
};

export type DocumentIntegrationCatalogItem = {
  id: string;
  label: string;
  status: string;
  source_module: string;
  source_table: string;
  entity_type: string;
};

export type DocumentIntegrationCatalogSearchResponse = {
  items: DocumentIntegrationCatalogItem[];
  limit: number;
  source_module: string;
  source_table: string;
};

async function jsonOrThrow<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    let message = `${fallback} (${response.status}).`;
    try {
      const payload = await response.json();
      message = typeof payload?.detail === "string" ? payload.detail : payload?.detail?.message || message;
    } catch {
      // Preserve the operational fallback.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function getDocumentIntegrationCatalog(
  tenant: string,
  sourceModule?: string,
): Promise<DocumentIntegrationCatalogResponse> {
  const query = sourceModule ? `?source_module=${encodeURIComponent(sourceModule)}` : "";
  const response = await fetch(
    `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/integration-catalog${query}`,
    { headers: authHeaders(), credentials: "same-origin" },
  );
  return jsonOrThrow<DocumentIntegrationCatalogResponse>(response, "The integration catalogue could not be loaded");
}

export async function searchDocumentIntegrationCatalog(
  tenant: string,
  params: { sourceModule: string; sourceTable: string; q?: string; limit?: number },
): Promise<DocumentIntegrationCatalogSearchResponse> {
  const query = new URLSearchParams({
    source_module: params.sourceModule,
    source_table: params.sourceTable,
    limit: String(params.limit || 25),
  });
  if (params.q?.trim()) query.set("q", params.q.trim());
  const response = await fetch(
    `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/integration-catalog/search?${query.toString()}`,
    { headers: authHeaders(), credentials: "same-origin" },
  );
  return jsonOrThrow<DocumentIntegrationCatalogSearchResponse>(response, "Integration records could not be searched");
}
