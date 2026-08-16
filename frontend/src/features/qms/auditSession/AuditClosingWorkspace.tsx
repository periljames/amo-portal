import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Download,
  FileCheck2,
  FileSignature,
  LockKeyhole,
  RefreshCw,
  ShieldAlert,
  Stamp,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { qmsResolveAudit } from "../../../services/qms";
import {
  adoptGeneratedAuditReport,
  getAuditClosureState,
  listAuditReportRevisions,
  recordAuditExecutionClosed,
  transitionAuditReport,
  type AuditReportRevision,
} from "../../../services/qmsAuditCloseout";
import {
  generateAuditAssuranceArtifact,
  getAuditOutputPolicy,
  listAuditAssuranceArtifacts,
  listAuditSignatureEvidence,
  signIssuedAuditReport,
} from "../../../services/qmsAuditClosingAssurance";
import {
  downloadGeneratedAuditReport,
  generateAuditClosingReport,
  getAuditReportComposition,
  type GeneratedAuditReportArtifact,
} from "../../../services/qmsAuditReportComposition";
import { saveDownloadedFile } from "../../../utils/downloads";
import { auditSessionPath } from "./auditSessionRoutes";
import "../../../styles/qms-audit-closing-workspace.css";

type Props = { amoCode: string; auditKey: string };

type TransitionAction = "SUBMIT" | "RETURN" | "APPROVE" | "ISSUE" | "CANCEL";

function bytes(value: number): string {
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${Math.round(value / 1024)} KB`;
  return `${value} B`;
}

function transitionLabel(revision: AuditReportRevision | null): { action: TransitionAction; label: string } | null {
  if (!revision) return null;
  if (revision.status === "DRAFT") return { action: "SUBMIT", label: "Submit for internal review" };
  if (revision.status === "INTERNAL_REVIEW") return { action: "APPROVE", label: "Approve report revision" };
  if (revision.status === "APPROVED") return { action: "ISSUE", label: "Issue approved report" };
  return null;
}

const AuditClosingWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [downloadBusy, setDownloadBusy] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [reauthValue, setReauthValue] = useState("");
  const [signReason, setSignReason] = useState("Closing meeting approval of the issued audit report.");

  const auditQuery = useQuery({
    queryKey: ["qms-closing-resolve", auditKey],
    queryFn: () => qmsResolveAudit(auditKey),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const compositionQuery = useQuery({
    queryKey: ["qms-audit-report-composition", amoCode, auditId],
    queryFn: ({ signal }) => getAuditReportComposition(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 1_500,
  });
  const revisionsQuery = useQuery({
    queryKey: ["qms-audit-report-revisions", amoCode, auditId],
    queryFn: ({ signal }) => listAuditReportRevisions(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 1_500,
  });
  const closureQuery = useQuery({
    queryKey: ["qms-audit-closure-state", amoCode, auditId],
    queryFn: ({ signal }) => getAuditClosureState(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 1_500,
  });
  const policyQuery = useQuery({
    queryKey: ["qms-audit-output-policy", amoCode],
    queryFn: ({ signal }) => getAuditOutputPolicy(amoCode, signal),
    enabled: Boolean(auditId),
    staleTime: 5_000,
  });
  const signaturesQuery = useQuery({
    queryKey: ["qms-audit-signatures", amoCode, auditId],
    queryFn: ({ signal }) => listAuditSignatureEvidence(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 1_500,
  });
  const assuranceArtifactsQuery = useQuery({
    queryKey: ["qms-audit-assurance-artifacts", amoCode, auditId],
    queryFn: ({ signal }) => listAuditAssuranceArtifacts(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 1_500,
  });

  const invalidateClosing = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-report-composition", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-report-revisions", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-closure-state", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-signatures", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-assurance-artifacts", amoCode, auditId] }),
    ]);
  };

  const generateMutation = useMutation({
    mutationFn: () => generateAuditClosingReport(amoCode, auditId),
    onSuccess: async () => { setLocalError(null); await invalidateClosing(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Closing report generation failed."),
  });
  const adoptMutation = useMutation({
    mutationFn: (artifactId: string) => adoptGeneratedAuditReport(amoCode, auditId, artifactId, "Adopt deterministic closing report for governed closing-meeting review."),
    onSuccess: async () => { setLocalError(null); await invalidateClosing(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Generated report adoption failed."),
  });
  const transitionMutation = useMutation({
    mutationFn: ({ revision, action }: { revision: AuditReportRevision; action: TransitionAction }) => transitionAuditReport(
      amoCode,
      auditId,
      revision.id,
      action,
      `${action.replaceAll("_", " ")} performed during the governed audit closing meeting.`,
    ),
    onSuccess: async () => { setLocalError(null); await invalidateClosing(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Report lifecycle transition failed."),
  });
  const signMutation = useMutation({
    mutationFn: () => signIssuedAuditReport(amoCode, auditId, reauthValue, signReason),
    onSuccess: async () => {
      setReauthValue("");
      setLocalError(null);
      await invalidateClosing();
    },
    onError: (cause) => {
      setReauthValue("");
      setLocalError(cause instanceof Error ? cause.message : "Electronic approval failed.");
    },
  });
  const executionCloseMutation = useMutation({
    mutationFn: () => recordAuditExecutionClosed(amoCode, auditId, "Audit execution closed during the closing meeting after report issue and electronic approval."),
    onSuccess: async () => { setLocalError(null); await invalidateClosing(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Audit execution close failed."),
  });
  const assuranceArtifactMutation = useMutation({
    mutationFn: (signatureId: string) => generateAuditAssuranceArtifact(amoCode, auditId, signatureId),
    onSuccess: async () => { setLocalError(null); await invalidateClosing(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Assurance artifact generation failed."),
  });

  const composition = compositionQuery.data;
  const pending = composition?.checklist_counts.NOT_VERIFIED || 0;
  const latestGenerated = composition?.artifacts[0] || null;
  const revisions = revisionsQuery.data?.items || [];
  const activeRevision = revisions.find((revision) => ["DRAFT", "INTERNAL_REVIEW", "APPROVED"].includes(revision.status)) || null;
  const issuedRevision = revisions.find((revision) => revision.status === "ISSUED") || null;
  const latestRevision = activeRevision || issuedRevision || revisions[0] || null;
  const lifecycleNext = transitionLabel(activeRevision);
  const closure = closureQuery.data;
  const signatures = signaturesQuery.data?.items || [];
  const currentSignature = issuedRevision
    ? signatures.find((signature) => signature.report_revision_id === issuedRevision.id && signature.artifact_sha256 === issuedRevision.sha256) || null
    : null;
  const policy = policyQuery.data?.current || null;
  const supplementaryPolicy = Boolean(policy && ["APPROVAL_LETTER", "CERTIFICATE", "ATTESTATION"].includes(policy.artifact_policy));
  const assuranceArtifacts = assuranceArtifactsQuery.data?.items || [];
  const currentAssuranceArtifact = currentSignature && issuedRevision
    ? assuranceArtifacts.find((artifact) => artifact.source_report_revision_id === issuedRevision.id && artifact.signature_evidence_id === currentSignature.id) || null
    : null;
  const canGenerate = Boolean(canManage && composition?.audit.actual_end && pending === 0);
  const canSign = Boolean(canManage && issuedRevision && !currentSignature && reauthValue.trim() && signReason.trim().length >= 8);
  const canExecutionClose = Boolean(canManage && currentSignature && closure?.execution_status !== "CLOSED" && closure?.execution_readiness.ready);
  const canGenerateAssurance = Boolean(canManage && supplementaryPolicy && currentSignature && closure?.execution_status === "CLOSED" && !currentAssuranceArtifact);

  const counts = useMemo(() => ({
    compliant: composition?.checklist_counts.COMPLIANT || 0,
    noncompliant: composition?.checklist_counts.NONCOMPLIANT || 0,
    observations: composition?.checklist_counts.OBSERVATION || 0,
    notApplicable: composition?.checklist_counts.NOT_APPLICABLE || 0,
  }), [composition?.checklist_counts]);

  const download = async (artifact: GeneratedAuditReportArtifact) => {
    setDownloadBusy(artifact.id);
    setLocalError(null);
    try {
      const blob = await downloadGeneratedAuditReport(amoCode, auditId, artifact.id);
      saveDownloadedFile(blob, artifact.filename);
    } catch (cause) {
      setLocalError(cause instanceof Error ? cause.message : "Generated report download failed.");
    } finally {
      setDownloadBusy(null);
    }
  };

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["qms-audit-output-policy", amoCode] });
    await invalidateClosing();
  };

  const loadError = auditQuery.error || compositionQuery.error || revisionsQuery.error || closureQuery.error || policyQuery.error || signaturesQuery.error || assuranceArtifactsQuery.error;
  if (auditQuery.isLoading || compositionQuery.isLoading || revisionsQuery.isLoading || closureQuery.isLoading || policyQuery.isLoading || signaturesQuery.isLoading || assuranceArtifactsQuery.isLoading) {
    return <div className="qms-audit-closing qms-audit-closing--loading">Preparing closing meeting workspace…</div>;
  }
  if (loadError || !auditQuery.data || !composition) {
    return <div className="qms-audit-closing qms-audit-closing--loading" role="alert"><AlertTriangle size={20} /> {loadError instanceof Error ? loadError.message : "Closing workspace unavailable."}</div>;
  }

  return (
    <div className="qms-audit-closing" role="region" aria-label="Audit closing meeting workspace">
      <header className="qms-audit-closing__header">
        <div><span>CLOSING MEETING · governed same-session issue</span><h1>{auditQuery.data.audit_ref} · {auditQuery.data.title}</h1></div>
        <div className="qms-audit-closing__header-actions"><button type="button" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</button><Link to={auditSessionPath(amoCode, auditKey, "live")}><X size={16} /> Exit closing</Link></div>
      </header>

      {localError ? <div className="qms-audit-closing__error" role="alert"><ShieldAlert size={16} /> {localError}</div> : null}

      <div className="qms-audit-closing__body">
        <main>
          <section className="qms-audit-closing__card">
            <header><FileCheck2 size={19} /><div><strong>1 · Freeze closing report</strong><small>Deterministic snapshot from authoritative audit, checklist, finding, CAR and preparation data.</small></div></header>
            <div className="qms-audit-closing__metrics">
              <div><strong>{counts.compliant}</strong><span>Compliant</span></div>
              <div><strong>{counts.noncompliant}</strong><span>Noncompliant</span></div>
              <div><strong>{counts.observations}</strong><span>Observations</span></div>
              <div><strong>{composition.findings_count}</strong><span>Findings</span></div>
              <div><strong>{composition.cars_count}</strong><span>CARs</span></div>
              <div><strong>{pending}</strong><span>Not verified</span></div>
            </div>
            {!composition.audit.actual_end ? <div className="qms-audit-closing__blocker"><AlertTriangle size={16} /> Fieldwork must be formally completed before a closing report snapshot can be generated.</div> : null}
            {pending > 0 ? <div className="qms-audit-closing__blocker"><AlertTriangle size={16} /> {pending} checklist item(s) remain NOT_VERIFIED.</div> : null}
            <div className="qms-audit-closing__actions">
              <button type="button" className="is-primary" disabled={!canGenerate || generateMutation.isPending} onClick={() => generateMutation.mutate()}>{generateMutation.isPending ? "Generating deterministic PDF…" : "Generate closing report draft"}</button>
              {latestGenerated ? <button type="button" onClick={() => void download(latestGenerated)} disabled={downloadBusy === latestGenerated.id}><Download size={15} /> {downloadBusy === latestGenerated.id ? "Downloading…" : "Preview / download latest"}</button> : null}
              {latestGenerated && !activeRevision ? <button type="button" disabled={!canManage || adoptMutation.isPending} onClick={() => adoptMutation.mutate(latestGenerated.id)}><FileSignature size={15} /> {adoptMutation.isPending ? "Adopting…" : "Adopt into governed revision"}</button> : null}
            </div>
            {latestGenerated ? (
              <dl className="qms-audit-closing__artifact">
                <div><dt>Artifact</dt><dd>{latestGenerated.filename}</dd></div>
                <div><dt>Generated</dt><dd>{new Date(latestGenerated.created_at).toLocaleString()}</dd></div>
                <div><dt>Size</dt><dd>{bytes(latestGenerated.size_bytes)}</dd></div>
                <div><dt>Template</dt><dd>{latestGenerated.template_version}</dd></div>
                <div className="is-wide"><dt>Source snapshot SHA-256</dt><dd><code>{latestGenerated.source_snapshot_hash}</code></dd></div>
                <div className="is-wide"><dt>Artifact SHA-256</dt><dd><code>{latestGenerated.sha256}</code></dd></div>
              </dl>
            ) : <p className="qms-audit-closing__empty">No generated closing report draft exists yet.</p>}
          </section>

          <section className="qms-audit-closing__card">
            <header><FileSignature size={19} /><div><strong>2 · Review, approve and issue</strong><small>Generated files do not become issued reports until this governed lifecycle completes.</small></div></header>
            <div className="qms-audit-closing__lifecycle">
              <div><span>Generated</span><strong>{latestGenerated ? "READY" : "PENDING"}</strong></div>
              <ArrowRight size={16} />
              <div><span>Governed revision</span><strong>{latestRevision ? `Rev ${latestRevision.revision_no} · ${latestRevision.status}` : "PENDING"}</strong></div>
              <ArrowRight size={16} />
              <div><span>Issued</span><strong>{issuedRevision ? `Rev ${issuedRevision.revision_no}` : "PENDING"}</strong></div>
            </div>
            {latestRevision ? <div className="qms-audit-closing__hash"><span>Controlled revision SHA-256</span><code>{latestRevision.sha256}</code></div> : null}
            <div className="qms-audit-closing__actions">
              {activeRevision && lifecycleNext ? <button type="button" className="is-primary" disabled={!canManage || transitionMutation.isPending} onClick={() => transitionMutation.mutate({ revision: activeRevision, action: lifecycleNext.action })}>{transitionMutation.isPending ? "Recording transition…" : lifecycleNext.label}</button> : null}
              {activeRevision?.status === "INTERNAL_REVIEW" ? <button type="button" disabled={!canManage || transitionMutation.isPending} onClick={() => transitionMutation.mutate({ revision: activeRevision, action: "RETURN" })}>Return to draft</button> : null}
            </div>
          </section>

          <section className="qms-audit-closing__card">
            <header><LockKeyhole size={19} /><div><strong>3 · Electronic approval evidence</strong><small>Bound to the exact ISSUED report revision and SHA-256 checksum.</small></div></header>
            {!issuedRevision ? <p className="qms-audit-closing__empty">Issue the governed report before electronic approval can be recorded.</p> : currentSignature ? (
              <dl className="qms-audit-closing__artifact">
                <div><dt>Signer</dt><dd>{currentSignature.signer_user_id}</dd></div>
                <div><dt>Method</dt><dd>PASSWORD RE-AUTH</dd></div>
                <div><dt>Signed</dt><dd>{currentSignature.signed_at ? new Date(currentSignature.signed_at).toLocaleString() : "—"}</dd></div>
                <div><dt>Purpose</dt><dd>{currentSignature.purpose.replaceAll("_", " ")}</dd></div>
                <div className="is-wide"><dt>Signed report SHA-256</dt><dd><code>{currentSignature.artifact_sha256}</code></dd></div>
                <div className="is-wide"><dt>Signature evidence digest</dt><dd><code>{currentSignature.signature_digest}</code></dd></div>
              </dl>
            ) : (
              <div className="qms-audit-closing__sign-form">
                <label><span>Approval reason</span><textarea rows={3} value={signReason} onChange={(event) => setSignReason(event.target.value)} /></label>
                <label><span>Re-authenticate to sign</span><input type="password" autoComplete="current-password" value={reauthValue} onChange={(event) => setReauthValue(event.target.value)} /></label>
                <button type="button" className="is-primary" disabled={!canSign || signMutation.isPending} onClick={() => signMutation.mutate()}><FileSignature size={15} /> {signMutation.isPending ? "Recording approval…" : "Sign issued report"}</button>
                <small>The re-authentication value is submitted for this action only and cleared after the attempt. This records governed electronic signature evidence; it is not represented as a PAdES signature embedded in the PDF.</small>
              </div>
            )}
          </section>

          <section className="qms-audit-closing__card">
            <header><Stamp size={19} /><div><strong>4 · Close execution and issue configured assurance output</strong><small>Certificate/approval/attestation exists only when tenant policy explicitly enables it.</small></div></header>
            <dl className="qms-audit-closing__artifact">
              <div><dt>Output policy</dt><dd>{policy ? `Rev ${policy.revision_no} · ${policy.artifact_policy.replaceAll("_", " ")}` : "Not configured"}</dd></div>
              <div><dt>Execution</dt><dd>{closure?.execution_status || "OPEN"}</dd></div>
              {policy?.artifact_title ? <div className="is-wide"><dt>Configured title</dt><dd>{policy.artifact_title}</dd></div> : null}
            </dl>
            {!policyQuery.data?.configured ? <div className="qms-audit-closing__blocker"><AlertTriangle size={16} /> No audit output policy is configured. The portal will not invent a certificate or approval artifact.</div> : null}
            {policy && ["NONE", "REPORT_ONLY"].includes(policy.artifact_policy) ? <p className="qms-audit-closing__empty">Current policy permits the governed report only; no supplementary certificate/approval/attestation will be generated.</p> : null}
            <div className="qms-audit-closing__actions">
              {closure?.execution_status !== "CLOSED" ? <button type="button" disabled={!canExecutionClose || executionCloseMutation.isPending} onClick={() => executionCloseMutation.mutate()}><CheckCircle2 size={15} /> {executionCloseMutation.isPending ? "Closing execution…" : "Close audit execution"}</button> : <span className="qms-audit-closing__ready"><CheckCircle2 size={15} /> Audit execution closed</span>}
              {supplementaryPolicy && currentSignature ? <button type="button" className="is-primary" disabled={!canGenerateAssurance || assuranceArtifactMutation.isPending} onClick={() => assuranceArtifactMutation.mutate(currentSignature.id)}><Stamp size={15} /> {assuranceArtifactMutation.isPending ? "Generating controlled artifact…" : currentAssuranceArtifact ? `${currentAssuranceArtifact.artifact_type.replaceAll("_", " ")} generated` : `Generate ${policy?.artifact_policy.replaceAll("_", " ")}`}</button> : null}
            </div>
            {currentAssuranceArtifact ? <div className="qms-audit-closing__issued-artifact"><strong>{currentAssuranceArtifact.filename}</strong><span>{bytes(currentAssuranceArtifact.size_bytes)} · SHA-256 <code>{currentAssuranceArtifact.sha256}</code></span></div> : null}
          </section>
        </main>

        <aside>
          <section className="qms-audit-closing__card qms-audit-closing__gates">
            <header><CheckCircle2 size={19} /><div><strong>Closing gates</strong><small>Authoritative backend readiness.</small></div></header>
            <ul>
              <li data-ready={Boolean(composition.audit.actual_end)}><span>Fieldwork completed</span><strong>{composition.audit.actual_end ? "Ready" : "Blocked"}</strong></li>
              <li data-ready={pending === 0}><span>Checklist resolved</span><strong>{pending === 0 ? "Ready" : `${pending} pending`}</strong></li>
              <li data-ready={Boolean(issuedRevision)}><span>Issued report revision</span><strong>{issuedRevision ? "Ready" : "Pending"}</strong></li>
              <li data-ready={Boolean(currentSignature)}><span>Electronic approval evidence</span><strong>{currentSignature ? "Ready" : "Pending"}</strong></li>
              <li data-ready={closure?.execution_readiness.ready === true}><span>Execution close readiness</span><strong>{closure?.execution_readiness.ready ? "Ready" : `${closure?.execution_readiness.blockers.length || 0} blocker(s)`}</strong></li>
              <li data-ready={closure?.execution_status === "CLOSED"}><span>Execution formally closed</span><strong>{closure?.execution_status === "CLOSED" ? "Closed" : "Open"}</strong></li>
            </ul>
            {closure?.execution_readiness.blockers.length ? <ul className="qms-audit-closing__blocker-list">{closure.execution_readiness.blockers.map((blocker, index) => <li key={`${blocker.type}-${blocker.id || index}`}><span>{blocker.type.replaceAll("_", " ")}</span><small>{blocker.reason}</small></li>)}</ul> : null}
          </section>

          <section className="qms-audit-closing__card qms-audit-closing__signature">
            <header><FileSignature size={19} /><div><strong>Integrity chain</strong><small>Revision → checksum → signer → policy → artifact.</small></div></header>
            <p>{issuedRevision ? `Issued report Rev ${issuedRevision.revision_no} is controlled at SHA-256 ${issuedRevision.sha256.slice(0, 16)}…` : "No issued report is available yet."}</p>
            <p>{currentSignature ? `Electronic approval evidence ${currentSignature.id} is bound to that exact checksum.` : "No current signature evidence is bound to the issued revision."}</p>
            {supplementaryPolicy ? <p>{currentAssuranceArtifact ? `Configured ${currentAssuranceArtifact.artifact_type.replaceAll("_", " ")} has been generated from the same integrity chain.` : `Policy requires ${policy?.artifact_policy.replaceAll("_", " ")} only after execution closure.`}</p> : null}
          </section>

          <Link className="qms-audit-closing__continue" to={auditSessionPath(amoCode, auditKey, "follow-up")}>Open Follow-up <ArrowRight size={16} /></Link>
        </aside>
      </div>
    </div>
  );
};

export default AuditClosingWorkspace;
