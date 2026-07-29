import { authHeaders } from "./auth";
import { apiPost } from "./crs";
import type { DocumentationNodeType } from "./documentation";

export type DocumentationAssistMode = "SEARCH" | "ASSIST" | "NAVIGATE";

export type DocumentationAssistSource = {
  id: string;
  rank: number;
  kind: "DOCUMENT" | "SECTION";
  manual_id: string;
  revision_id: string;
  code: string;
  title: string;
  node_type: DocumentationNodeType;
  hierarchy_path?: string | null;
  heading?: string | null;
  section_id?: string | null;
  anchor?: string | null;
  page_number?: number | null;
  snippet: string;
  score: number;
  reader_url: string;
  source_type?: string | null;
  executable: boolean;
  reason: string;
};

export type DocumentationAssistResponse = {
  query: string;
  mode: DocumentationAssistMode;
  provider_mode: "DETERMINISTIC" | "OPENAI";
  answer: string;
  citations: string[];
  sources: DocumentationAssistSource[];
  navigation: {
    primary_source_id?: string | null;
    reader_url?: string | null;
    manual_id?: string | null;
    revision_id?: string | null;
    page_number?: number | null;
    anchor?: string | null;
  };
  capabilities: {
    assisted_search: boolean;
    external_ai_enabled: boolean;
    answers_are_advisory: boolean;
    controlled_source_is_authoritative: boolean;
  };
  warning?: string | null;
};

export type DocumentationAssistRequest = {
  query: string;
  mode?: DocumentationAssistMode;
  manual_id?: string | null;
  revision_id?: string | null;
  page_number?: number | null;
  limit?: number;
};

function tenantPath(tenant: string): string {
  return encodeURIComponent(tenant.toLowerCase());
}

export async function assistDocumentation(
  tenant: string,
  payload: DocumentationAssistRequest,
): Promise<DocumentationAssistResponse> {
  return apiPost<DocumentationAssistResponse>(
    `/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/assist`,
    payload,
    { headers: authHeaders({ "Content-Type": "application/json" }) },
  );
}
