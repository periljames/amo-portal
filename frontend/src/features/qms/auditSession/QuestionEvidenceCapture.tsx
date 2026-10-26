import { useRef, useState } from "react";
import { Camera, Paperclip, Upload } from "lucide-react";
import { enqueueOfflineAuditEvidence } from "../../../services/qmsOfflineAuditEvidence";
import { createEvidenceMutationId } from "../../../services/qmsAuditEvidence";
import { requestPortalOfflineSync } from "../../../services/portalOfflineSync";
import type { ChecklistExecutionGovernanceRow } from "../../../services/qmsChecklistExecutionGovernance";

export default function QuestionEvidenceCapture({ amoCode, auditId, item, disabled, pending = 0 }: {
  amoCode: string; auditId: string; item: ChecklistExecutionGovernanceRow; disabled: boolean; pending?: number;
}) {
  const upload = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const capture = async (input: HTMLInputElement) => {
    const files = [...(input.files || [])];
    if (!files.length) return;
    setBusy(true); setError("");
    try {
      for (const file of files) await enqueueOfflineAuditEvidence({
        amoCode, auditId, checklistItemId: item.checklist_item_id, findingId: item.finding_id,
        file, clientMutationId: createEvidenceMutationId(), baseVersion: item.entity_version,
      });
      requestPortalOfflineSync(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Evidence could not be saved on this device. Keep the original and retry.");
    } finally { input.value = ""; setBusy(false); }
  };
  return <div className="audit-question-attachments">
    <details><summary aria-label={`Attach evidence for ${item.checklist_ref || "question"}`} aria-disabled={disabled || busy}>
      <Paperclip size={16} aria-hidden /><span>{busy ? "Saving…" : "Attach"}</span>{pending ? <small>{pending} pending</small> : null}
    </summary><div className="audit-question-attachments__choices">
      <button type="button" disabled={disabled || busy} onClick={() => upload.current?.click()}><Upload size={16} />Upload files</button>
      <button type="button" disabled={disabled || busy} onClick={() => camera.current?.click()}><Camera size={16} />Take photo</button>
    </div></details>
    <input ref={upload} type="file" multiple hidden aria-label="Upload question evidence" onChange={(event) => void capture(event.currentTarget)} />
    <input ref={camera} type="file" accept="image/*" capture="environment" hidden aria-label="Photograph question evidence" onChange={(event) => void capture(event.currentTarget)} />
    {error ? <small role="alert">{error}</small> : null}
  </div>;
}
