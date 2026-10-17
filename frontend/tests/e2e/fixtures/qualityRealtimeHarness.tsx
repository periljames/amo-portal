import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import QualityDataFreshnessCoordinator from "../../../src/components/QMS/QualityDataFreshnessCoordinator";
import { apiRequest } from "../../../src/services/apiClient";
import { saveToken } from "../../../src/services/auth";
import { setApiBaseRuntime } from "../../../src/services/config";
import { publishQmsRealtimeEvent, publishQmsRealtimeState } from "../../../src/services/qmsAuditRealtime";

const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false } } });
function Data({ id, module }: { id: string; module: string }) {
  const query = useQuery({ queryKey: [module, "live-audit-checklist", "safarilink", id],
    queryFn: () => apiRequest<{ id: string; value: number }>(`/__realtime_fixture__/${id}`, { cacheTtlMs: 30_000, offline: { cache: false, allowStaleFallback: false } }),
  });
  return <output data-testid={id}>{query.data?.value ?? "loading"}</output>;
}
export function mount() {
  saveToken("isolated-browser-fixture-only");
  setApiBaseRuntime(location.origin);
  createRoot(document.getElementById("root")!).render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/maintenance/safarilink/quality/audits/audit-a/live"]}>
    <QualityDataFreshnessCoordinator /><Data id="audit-a" module="qms" /><Data id="audit-b" module="qms" /><Data id="fleet" module="fleet" />
  </MemoryRouter></QueryClientProvider>);
}
export function event(auditId?: string, reset = false) {
  publishQmsRealtimeEvent({ id: crypto.randomUUID(), event: reset ? "reset" : "qms.audit.checklist_item.updated", data: { type: "qms.audit.checklist_item.updated", metadata: { module: "quality", auditId } } });
}
export const state = publishQmsRealtimeState;
