import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, FileCheck2, ShieldAlert, X } from "lucide-react";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { qmsListFindings, qmsResolveAudit } from "../../../services/qms";
import { listAuditEvidence, type AuditEvidenceArtifact } from "../../../services/qmsAuditEvidence";
import {
  listAuditFindingReleases,
  releaseAuditFinding,
  type AuditFindingReleaseState,
} from "../../../services/qmsAuditExternalAccess";
import { listChecklistExecutionGovernance } from "../../../services/qmsChecklistExecutionGovernance";
import "../../../styles/qms-live-finding-release.css";

type Props = { amoCode: string; auditKey: string };

type DecisionDraft = {
  findingId: string;
  action: "RELEASED" | "WITHDRAWN";
  includeObjectiveEvidence: boolean;
  evidenceArtifactIds: string[];
  reason: string;
};

function releasedArtifactIds(release: AuditFindingReleaseState | undefined): string[] {
  return (release?.released_evidence_refs || []).flatMap((ref) => {
    if (!ref || typeof ref === "string") return [];
    return typeof ref.artifact_id === "string" ? [ref.artifact_id] : [];
  });
}

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
  const evidenceQuery = useQuery({
    queryKey: ["qms-live-audit-release-evidence", amoCode, auditId],
    queryFn: ({ signal }) => listAuditEvidence(amoCode, auditId, null, null, signal),
    enabled: Boolean(canManage && auditId),
    staleTime: 1_500,
  });
  const checklistQuery = useQuery({
    queryKey: ["qms-live-audit-release-checklist", amoCode, auditId],
    queryFn: ({ signal }) => listChecklistExecutionGovernance(amoCode, auditId, signal),
    enabled: Boolean(canManage && auditId),
    staleTime: 1_500,
  });

  const releaseByFinding = useMemo(() => {
    const map = new Map<string, AuditFindingReleaseState>();
    for (const row of releasesQuery.data?.items || []) map.set(row.finding_id, row);
    return map;
  }, [releasesQuery.data?.items]);

  const evidenceByFinding = useMemo(() => {
    const checklistIds = new Map<string, Set<string>>();
    for (const row of checklistQuery.data?.items || []) {
      if (!row.finding_id) continue;
      const current = checklistIds.get(row.finding_id) || new Set<string>();
      current.add(row.checklist_item_id);
      checklistIds.set(row.finding_id, current);
    }
    const map = new Map<string, AuditEvidenceArtifact[]>();
    for (const finding of findingsQuery.data || []) {
      const linkedChecklist = checklistIds.get(finding.id) || new Set<string>();
      map.set(
        finding.id,
        (evidenceQuery.data?.items || []).filter((artifact) =>
          artifact.finding_id === finding.id || Boolean(artifact.checklist_item_id && linkedChecklist.has(artifact.checklist_item_id)),
        ),
      );
    }
    return map;
  }, [checklistQuery.data?.items, evidenceQuery.data?.items, findingsQuery.data]);

  const decisionMutation = useMutation({
    mutationFn: (decision: DecisionDraft) => releaseAuditFinding(amoCode, auditId, decision.findingId, {
      action: decision.action,
      include_objective_evidence: decision.action === "RELEASED" && decision.includeObjectiveEvidence,
      released_evidence_refs: decision.action === "RELEASED"
        ? decision.evidenceArtifactIds.map((artifactId) => ({ artifact_id: artifactId }))
        : [],
      reason: decision.reason.trim(),
    }),
    onSuccess: async () => {
      setDraft(null);
      setError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["qms-live-audit-finding-releases", amoCode, auditId] }),
        queryClient.invalidateQueries({ queryKey: ["qms-live-audit-findings", auditId] }),
        queryClient.invalidateQueries({ queryKey: ["qms", "live-audit-findings", auditId] }),
        queryClient.invalidateQueries({ queryKey: ["qms", "audit-session", amoCode, auditId] }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
      ]);
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : "Finding release decision failed."),
  });

  if (!canManage) return null;
  const findings = findingsQuery.data || [];
  const releasedCount = findings.filter((finding) => releaseByFinding.get(finding.id)?.action === "RELEASED").length;
  const draftEvidence = draft ? evidenceByFinding.get(draft.findingId) || [] : [];

  return (
    <>
      <button className="qms-live-release-launcher" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <Eye size={16} /> Auditee releases <span>{releasedCount}/{findings.length}</span>
      </button>
      {open ? (
        <aside className="qms-live-release-panel" aria-label="Auditee finding release controls">
          <header><div><span>EXTERNAL VISIBILITY</span><strong>Released findings</strong></div><button type="button" onClick={() => setOpen(false)} aria-label="Close finding release controls"><X size={17} /></button></header>
          <p>Recording a finding does not disclose it. Release is an explicit server-side projection. Governed evidence files must be selected individually; storage paths and free-form file references cannot cross this boundary.</p>
          {error ? <div className="qms-live-release-panel__error" role="alert"><ShieldAlert size={15} /> {error}</div> : null}
          <div className="qms-live-release-panel__list">
            {findings.map((finding) => {
              const release = releaseByFinding.get(finding.id);
              const isReleased = release?.action === "RELEASED";
              const availableEvidence = evidenceByFinding.get(finding.id) || [];
              const releasedFiles = releasedArtifactIds(release).length;
              return (
                <article key={finding.id}>
                  <div><span>{finding.level || finding.severity || "Finding"}</span><strong>{finding.finding_ref || "Finding"}</strong><small>{finding.requirement_ref || "No requirement reference"}</small><p>{finding.description}</p><small>{availableEvidence.length} governed evidence file{availableEvidence.length === 1 ? "" : "s"} linked · {releasedFiles} currently released</small></div>
                  <div className="qms-live-release-panel__state">{isReleased ? <><Eye size={14} /> Released</> : <><EyeOff size={14} /> Auditor only</>}</div>
                  <button type="button" onClick={() => setDraft({
                    findingId: finding.id,
                    action: isReleased ? "WITHDRAWN" : "RELEASED",
                    includeObjectiveEvidence: release?.include_objective_evidence || false,
                    evidenceArtifactIds: isReleased ? releasedArtifactIds(release) : [],
                    reason: "",
                  })}>{isReleased ? "Withdraw" : "Release"}</button>
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
            {draft.action === "RELEASED" ? (
              <>
                <label className="qms-live-release-decision__check"><input type="checkbox" checked={draft.includeObjectiveEvidence} onChange={(event) => setDraft((current) => current ? { ...current, includeObjectiveEvidence: event.target.checked } : current)} /> Include the finding's objective-evidence text in the external view</label>
                <fieldset className="qms-live-release-decision__evidence">
                  <legend>Governed evidence files released with this finding</legend>
                  {!draftEvidence.length ? <p>No governed file artifacts are linked to this finding/checklist yet.</p> : draftEvidence.map((artifact) => (
                    <label key={artifact.id}>
                      <input type="checkbox" checked={draft.evidenceArtifactIds.includes(artifact.id)} onChange={(event) => setDraft((current) => current ? {
                        ...current,
                        evidenceArtifactIds: event.target.checked
                          ? [...new Set([...current.evidenceArtifactIds, artifact.id])]
                          : current.evidenceArtifactIds.filter((id) => id !== artifact.id),
                      } : current)} />
                      <FileCheck2 size={14} />
                      <span><strong>{artifact.filename}</strong><small>{Math.ceil(artifact.size_bytes / 1024)} KB · {artifact.source_type.replaceAll("_", " ")} · SHA {artifact.sha256.slice(0, 12)}…</small></span>
                    </label>
                  ))}
                </fieldset>
              </>
            ) : null}
            <label><span>Decision reason</span><textarea rows={4} value={draft.reason} onChange={(event) => setDraft((current) => current ? { ...current, reason: event.target.value } : current)} placeholder="Record why this finding is being released or withdrawn." /></label>
            <p>Private auditor notes are never included. The server revalidates every selected artifact against this audit/finding relationship before release.</p>
            <footer><button type="button" onClick={() => setDraft(null)}>Cancel</button><button type="button" className="is-primary" disabled={draft.reason.trim().length < 3 || decisionMutation.isPending} onClick={() => decisionMutation.mutate(draft)}>{decisionMutation.isPending ? "Saving…" : draft.action === "RELEASED" ? "Release finding" : "Withdraw finding"}</button></footer>
          </section>
        </div>
      ) : null}
    </>
  );
};

export default LiveFindingReleasePanel;
