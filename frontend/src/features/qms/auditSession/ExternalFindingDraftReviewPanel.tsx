import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CornerDownLeft, FileWarning, X } from "lucide-react";

import { qmsResolveAudit } from "../../../services/qms";
import {
  listExternalFindingDraftsForQuality,
  promoteExternalFindingDraft,
  returnExternalFindingDraft,
} from "../../../services/qmsExternalFindingDraftReview";
import "../../../styles/qms-external-finding-draft-review.css";

type Props = { amoCode: string; auditKey: string };

const ExternalFindingDraftReviewPanel: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(true);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const auditQuery = useQuery({
    queryKey: ["qms", "external-draft-review-audit", auditKey],
    queryFn: () => qmsResolveAudit(auditKey),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const draftsQuery = useQuery({
    queryKey: ["qms", "external-finding-drafts", amoCode, auditId],
    queryFn: ({ signal }) => listExternalFindingDraftsForQuality(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 1_000,
    refetchInterval: 3_000,
  });

  const actionable = useMemo(
    () => (draftsQuery.data?.items || []).filter((draft) => draft.status === "SUBMITTED"),
    [draftsQuery.data?.items],
  );

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["qms"] });
  };
  const returnMutation = useMutation({
    mutationFn: ({ draftId, reviewNote }: { draftId: string; reviewNote: string }) => returnExternalFindingDraft(
      amoCode,
      auditId,
      draftId,
      { reason: "Quality returned external finding draft for revision.", review_note: reviewNote },
    ),
    onSuccess: refresh,
  });
  const promoteMutation = useMutation({
    mutationFn: ({ draftId, reviewNote }: { draftId: string; reviewNote: string }) => promoteExternalFindingDraft(
      amoCode,
      auditId,
      draftId,
      { reason: "Quality accepted and promoted the submitted external finding draft.", review_note: reviewNote || null },
    ),
    onSuccess: refresh,
  });

  if (!auditId || draftsQuery.isLoading || !actionable.length) return null;
  const mutationError = returnMutation.error || promoteMutation.error;

  return (
    <aside className={`qms-external-draft-review${open ? " is-open" : ""}`} aria-label="External finding drafts pending Quality review">
      <button type="button" className="qms-external-draft-review__toggle" onClick={() => setOpen((value) => !value)}>
        <FileWarning size={16} /> External drafts · {actionable.length}
      </button>
      {open ? <div className="qms-external-draft-review__body">
        <header><div><strong>External finding drafts</strong><small>Submitted proposals remain drafts until Quality explicitly promotes them.</small></div><button type="button" onClick={() => setOpen(false)} aria-label="Close external draft review"><X size={16} /></button></header>
        {draftsQuery.error ? <div role="alert"><AlertTriangle size={14} /> {draftsQuery.error instanceof Error ? draftsQuery.error.message : "Draft review unavailable."}</div> : null}
        {mutationError ? <div role="alert"><AlertTriangle size={14} /> {mutationError instanceof Error ? mutationError.message : "Draft review action failed."}</div> : null}
        <div className="qms-external-draft-review__list">
          {actionable.map((draft) => (
            <article key={draft.id}>
              <span>{draft.draft_type.replaceAll("_", " ")} · {draft.proposed_level}</span>
              <strong>{draft.requirement_ref || "No requirement reference"}</strong>
              <p>{draft.description}</p>
              <small>External participant {draft.participant_id.slice(0, 8)} · draft {draft.id.slice(0, 8)}</small>
              <label><span>Quality review note</span><textarea rows={2} value={notes[draft.id] || ""} onChange={(event) => setNotes((current) => ({ ...current, [draft.id]: event.target.value }))} placeholder="Decision rationale or revision instructions" /></label>
              <footer>
                <button type="button" disabled={returnMutation.isPending || promoteMutation.isPending || (notes[draft.id] || "").trim().length < 4} onClick={() => returnMutation.mutate({ draftId: draft.id, reviewNote: (notes[draft.id] || "").trim() })}><CornerDownLeft size={14} /> Return for revision</button>
                <button type="button" disabled={returnMutation.isPending || promoteMutation.isPending} onClick={() => promoteMutation.mutate({ draftId: draft.id, reviewNote: (notes[draft.id] || "").trim() })}><CheckCircle2 size={14} /> Promote to official finding</button>
              </footer>
            </article>
          ))}
        </div>
      </div> : null}
    </aside>
  );
};

export default ExternalFindingDraftReviewPanel;
