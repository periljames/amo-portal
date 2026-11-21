import { useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LiveAuditEvidenceStrip from "../../../src/features/qms/auditSession/LiveAuditEvidenceStrip";
import type { ChecklistExecutionGovernanceRow } from "../../../src/services/qmsChecklistExecutionGovernance";

const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const item = { checklist_item_id: "question", audit_id: "audit", entity_version: 1 } as ChecklistExecutionGovernanceRow;
function Harness() {
  const [capture, setCapture] = useState({ busy: false, hasDraft: false });
  const [revision, setRevision] = useState(0);
  return <QueryClientProvider client={client}>
    <button onClick={() => setRevision(value => value + 1)}>Parent update {revision}</button>
    <output aria-label="Capture state">{capture.hasDraft ? "Draft selected" : "No draft"}</output>
    <LiveAuditEvidenceStrip amoCode="test" auditId="audit" item={item} canManage
      onChanged={() => {}} onError={() => {}} onNotice={() => {}}
      onCaptureStateChange={state => setCapture(state)} />
  </QueryClientProvider>;
}
export function mount() { createRoot(document.getElementById("root")!).render(<Harness />); }
