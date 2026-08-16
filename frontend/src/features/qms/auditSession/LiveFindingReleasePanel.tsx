import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, ShieldAlert, X } from "lucide-react";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { qmsListFindings, qmsResolveAudit } from "../../../services/qms";
import {
  listAuditFindingReleases,
  releaseAuditFinding,
  type AuditFindingReleaseState,
} from "../../../services/qmsAuditExternalAccess";
import "../../../styles/qms-live-finding-release.css";

type Props = { amoCode: string; auditKey: string };

type DecisionDraft = {
  findingId: string;
  action: "RELEASED" | "WITHDRAWN";
  includeObjectiveEvidence: boolean;
  reason: string;
};

const LiveFindingReleasePanel: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<DecisionDraft | null>(null);
  const [error, setError] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: ["qms-live-release-resolve", auditKey],
    queryFn: () => qmsResolveAudit(auditKey),
    enabled: canManage,
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const findingsQuery = useQuery({
    queryKey: ["qms-live-audit-findings", auditId],
    queryFn: () => qmsListFindings(auditId),
    enabled: Boolean(canManage && auditId),
    staleTime: 1_500,
  });
  const releasesQuery = useQuery({
    queryKey: ["qms-live-audit-finding-releases", amoCode, auditId],
    queryFn: ({ signal }) => listAuditFindingReleases(amoCode, auditId, signal),
    enabled: Boolean(canManage && auditId),
    staleTime: 1_500,
  });

  const releaseByFinding = useMemo(() => {
    const map = new Map<string, AuditFindingReleaseState>();
    for (const row of releasesQuery.data?.items || []) map.set(row.finding_id, row);
    return map;
  }, [releasesQuery.data?.items]);

  const decisionMutation = useMutation({
    mutationFn: (decision: DecisionDraft) => releaseAuditFinding(amoCode, auditId, decision.findingId, {
      action: decision.action,
      include_objective_evidence: decision.includeObjectiveEvidence,
      released_evidence_refs: [],
      reason: decision.reason.trim(),
    }),
    onSuccess: async () => {
      setDraft(null);
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["qms-live-audit-finding-releases", amoCode, auditId] });
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : "Finding release decision failed."),
  });

  if (!canManage) return null;
  const findings = findingsQuery.data || [];
  const releasedCount = findings.filter((finding) => releaseByFinding.get(finding.id)?.action === "RELEASED").length;

  return (
    <>
      <button className="qms-live-release-launcher" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <Eye size={16} /> Auditee releases <span>{releasedCount}/{findings.length}</span>
      </button>
      {open ? (
        <aside className="qms-live-release-panel" aria-label="Auditee finding release controls">
          <header><div><span>EXTERNAL VISIBILITY</span><strong>Released findings</strong></div><button type="button" onClick={() => setOpen(false)} aria-label="Close finding release controls"><X size={17} /></button></header>
          <p>Recording a finding does not disclose it. Only an explicit release below makes the finding visible to an authorised auditee guest.</p>
          {error ? <div className="qms-live-release-panel__error" role="alert"><ShieldAlert size={15} /> {error}</div> : null}
          <div className="qms-live-release-panel__list">
            {findings.map((finding) => {
              const release = releaseByFinding.get(finding.id);
              const isReleased = release?.action === "RELEASED";
              return (
                <article key={finding.id}>
                  <div><span>{finding.level || finding.severity || "Finding"}</span><strong>{finding.finding_ref || "Finding"}</strong><small>{finding.requirement_ref || "No requirement reference"}</small><p>{finding.description}</p></div>
                  <div className="qms-live-release-panel__state">{isReleased ? <><Eye size={14} /> Released</> : <><EyeOff size={14} /> Auditor only</>}</div>
                  <button type="button" onClick={() => setDraft({ findingId: finding.id, action: isReleased ? "WITHDRAWN" : "RELEASED", includeObjectiveEvidence: false, reason: "" })}>{isReleased ? "Withdraw" : "Release"}</button>
                </article>
              );
            })}
            {!findings.length ? <div className="qms-live-release-panel__empty">No governed findings have been recorded yet.</div> : null}
          </div>
        </aside>
      ) : null}

      {draft ? (
        <div className="qms-live-release-decision-backdrop">
          <section className="qms-live-release-decision" role="dialog" aria-modal="true" aria-label={`${draft.action === "RELEASED" ? "Release" : "Withdraw"} finding`}>
            <header><strong>{draft.action === "RELEASED" ? "Release finding to auditee" : "Withdraw finding from auditee view"}</strong><button type="button" onClick={() => setDraft(null)} aria-label="Close"><X size={17} /></button></header>
            {draft.action === "RELEASED" ? <label className="qms-live-release-decision__check"><input type="checkbox" checked={draft.includeObjectiveEvidence} onChange={(event) => setDraft((current) => current ? { ...current, includeObjectiveEvidence: event.target.checked } : current)} /> Include the finding's objective-evidence text in the external view</label> : null}
            <label><span>Decision reason</span><textarea rows={4} value={draft.reason} onChange={(event) => setDraft((current) => current ? { ...current, reason: event.target.value } : current)} placeholder="Record why this finding is being released or withdrawn." /></label>
            <p>Private auditor notes are never included by this decision. Evidence files require their own released reference.</p>
            <footer><button type="button" onClick={() => setDraft(null)}>Cancel</button><button type="button" className="is-primary" disabled={draft.reason.trim().length < 3 || decisionMutation.isPending} onClick={() => decisionMutation.mutate(draft)}>{decisionMutation.isPending ? "Saving…" : draft.action === "RELEASED" ? "Release finding" : "Withdraw finding"}</button></footer>
          </section>
        </div>
      ) : null}
    </>
  );
};

export default LiveFindingReleasePanel;
