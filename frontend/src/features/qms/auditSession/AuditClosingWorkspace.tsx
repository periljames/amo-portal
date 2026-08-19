import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  ExternalLink,
  FileCheck2,
  FileSignature,
  Fingerprint,
  KeyRound,
  RefreshCw,
  ShieldAlert,
  Stamp,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import {
  createCredential,
  decodeCreationOptions,
  decodeRequestOptions,
  getAssertion,
  isSecureContextAvailable,
  isWebAuthnSupported,
  serializeAssertionCredential,
  serializeRegistrationCredential,
} from "../../../lib/webauthn";
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
  createAuditVerificationToken,
  generateAuditAssuranceArtifact,
  getApprovedAuditReportSignatureOptions,
  getAuditOutputPolicy,
  getAuditWebAuthnRegistrationOptions,
  listAuditAssuranceArtifacts,
  listAuditClosingAcknowledgements,
  listAuditSignatureEvidence,
  listAuditWebAuthnCredentials,
  verifyApprovedAuditReportSignature,
  verifyAuditWebAuthnRegistration,
  type AuditSignatureEvidence,
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
type CeremonyBusy = "register" | "sign" | "verify-link" | null;

function bytes(value: number): string {
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${Math.round(value / 1024)} KB`;
  return `${value} B`;
}

function sameRevisionSignature(revision: AuditReportRevision | null, signatures: AuditSignatureEvidence[]): AuditSignatureEvidence | null {
  if (!revision) return null;
  return signatures.find((signature) =>
    signature.method === "WEBAUTHN" &&
    signature.purpose === "APPROVED_REPORT" &&
    signature.report_revision_id === revision.id &&
    signature.artifact_sha256 === revision.sha256
  ) || null;
}

const AuditClosingWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [downloadBusy, setDownloadBusy] = useState<string | null>(null);
  const [ceremonyBusy, setCeremonyBusy] = useState<CeremonyBusy>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [passkeyNickname, setPasskeyNickname] = useState("Quality approval passkey");
  const [signReason, setSignReason] = useState("Quality approval of the exact governed audit report presented at the closing meeting.");
  const [verificationUrl, setVerificationUrl] = useState<string | null>(null);

  const auditQuery = useQuery({ queryKey: ["qms-closing-resolve", auditKey], queryFn: () => qmsResolveAudit(auditKey), staleTime: 5_000 });
  const auditId = auditQuery.data?.id || "";
  const compositionQuery = useQuery({ queryKey: ["qms-audit-report-composition", amoCode, auditId], queryFn: ({ signal }) => getAuditReportComposition(amoCode, auditId, signal), enabled: Boolean(auditId), staleTime: 1_500 });
  const revisionsQuery = useQuery({ queryKey: ["qms-audit-report-revisions", amoCode, auditId], queryFn: ({ signal }) => listAuditReportRevisions(amoCode, auditId, signal), enabled: Boolean(auditId), staleTime: 1_500 });
  const closureQuery = useQuery({ queryKey: ["qms-audit-closure-state", amoCode, auditId], queryFn: ({ signal }) => getAuditClosureState(amoCode, auditId, signal), enabled: Boolean(auditId), staleTime: 1_500 });
  const policyQuery = useQuery({ queryKey: ["qms-audit-output-policy", amoCode], queryFn: ({ signal }) => getAuditOutputPolicy(amoCode, signal), enabled: Boolean(auditId), staleTime: 5_000 });
  const signaturesQuery = useQuery({ queryKey: ["qms-audit-signatures", amoCode, auditId], queryFn: ({ signal }) => listAuditSignatureEvidence(amoCode, auditId, signal), enabled: Boolean(auditId), staleTime: 1_500 });
  const acknowledgementsQuery = useQuery({ queryKey: ["qms-audit-closing-acks", amoCode, auditId], queryFn: ({ signal }) => listAuditClosingAcknowledgements(amoCode, auditId, signal), enabled: Boolean(auditId), staleTime: 1_500 });
  const passkeysQuery = useQuery({ queryKey: ["qms-audit-passkeys", amoCode], queryFn: ({ signal }) => listAuditWebAuthnCredentials(amoCode, signal), enabled: Boolean(auditId) && canManage, staleTime: 3_000 });
  const assuranceArtifactsQuery = useQuery({ queryKey: ["qms-audit-assurance-artifacts", amoCode, auditId], queryFn: ({ signal }) => listAuditAssuranceArtifacts(amoCode, auditId, signal), enabled: Boolean(auditId), staleTime: 1_500 });

  const invalidateClosing = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-report-composition", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-report-revisions", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-closure-state", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-signatures", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-closing-acks", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-passkeys", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-assurance-artifacts", amoCode, auditId] }),
    ]);
  };

  const generateMutation = useMutation({
    mutationFn: () => generateAuditClosingReport(amoCode, auditId),
    onSuccess: async () => { setLocalError(null); setNotice("Closing report snapshot generated from the governed fieldwork state."); await invalidateClosing(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Closing report generation failed."),
  });
  const adoptMutation = useMutation({
    mutationFn: (artifactId: string) => adoptGeneratedAuditReport(amoCode, auditId, artifactId, "Adopt deterministic closing report for governed closing-meeting review."),
    onSuccess: async () => { setLocalError(null); setNotice("Generated report adopted as a governed draft revision for the closing meeting."); await invalidateClosing(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Generated report adoption failed."),
  });
  const transitionMutation = useMutation({
    mutationFn: ({ revision, action }: { revision: AuditReportRevision; action: "SUBMIT" | "RETURN" | "APPROVE" | "ISSUE" | "CANCEL" }) => transitionAuditReport(amoCode, auditId, revision.id, action, `${action.replaceAll("_", " ")} performed in the governed audit closing workflow.`),
    onSuccess: async (_, variables) => { setLocalError(null); setNotice(`${variables.action.replaceAll("_", " ")} recorded against the governed report revision.`); await invalidateClosing(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Report lifecycle transition failed."),
  });
  const executionCloseMutation = useMutation({
    mutationFn: () => recordAuditExecutionClosed(amoCode, auditId, "Audit execution closed after governed report issue and passkey approval; follow-up obligations remain independently controlled."),
    onSuccess: async () => { setLocalError(null); setNotice("Execution closed. CAR/CAPA follow-up remains open until its own closure gates are satisfied."); await invalidateClosing(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Audit execution close failed."),
  });
  const assuranceArtifactMutation = useMutation({
    mutationFn: (signatureId: string) => generateAuditAssuranceArtifact(amoCode, auditId, signatureId),
    onSuccess: async () => { setLocalError(null); setNotice("Policy-controlled assurance artifact generated from the issued report and signature evidence."); await invalidateClosing(); },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Assurance artifact generation failed."),
  });

  const composition = compositionQuery.data;
  const pending = composition?.checklist_counts.NOT_VERIFIED || 0;
  const latestGenerated = composition?.artifacts[0] || null;
  const revisions = revisionsQuery.data?.items || [];
  const activeRevision = revisions.find((revision) => ["DRAFT", "INTERNAL_REVIEW", "APPROVED"].includes(revision.status)) || null;
  const issuedRevision = revisions.find((revision) => revision.status === "ISSUED") || null;
  const currentRevision = activeRevision || issuedRevision || revisions[0] || null;
  const signatures = signaturesQuery.data?.items || [];
  const currentSignature = sameRevisionSignature(currentRevision, signatures);
  const acknowledgements = acknowledgementsQuery.data?.items || [];
  const currentAcknowledgement = currentRevision ? acknowledgements.find((item) => item.report_revision_id === currentRevision.id && item.report_sha256 === currentRevision.sha256) || null : null;
  const passkeys = (passkeysQuery.data?.items || []).filter((item) => item.is_active);
  const closure = closureQuery.data;
  const policy = policyQuery.data?.current || null;
  const supplementaryPolicy = Boolean(policy && ["APPROVAL_LETTER", "CERTIFICATE", "ATTESTATION"].includes(policy.artifact_policy));
  const assuranceArtifacts = assuranceArtifactsQuery.data?.items || [];
  const currentAssuranceArtifact = issuedRevision && currentSignature ? assuranceArtifacts.find((artifact) => artifact.source_report_revision_id === issuedRevision.id && artifact.signature_evidence_id === currentSignature.id) || null : null;
  const canGenerate = Boolean(canManage && composition?.audit.actual_end && pending === 0);
  const canSubmit = Boolean(canManage && activeRevision?.status === "DRAFT");
  const canApprove = Boolean(canManage && activeRevision?.status === "INTERNAL_REVIEW");
  const canSign = Boolean(canManage && activeRevision?.status === "APPROVED" && !currentSignature);
  const canIssue = Boolean(canManage && activeRevision?.status === "APPROVED" && currentSignature);
  const canExecutionClose = Boolean(canManage && issuedRevision && currentSignature && closure?.execution_status !== "CLOSED" && closure?.execution_readiness.ready);
  const canGenerateAssurance = Boolean(canManage && supplementaryPolicy && currentSignature && issuedRevision && !currentAssuranceArtifact);

  const counts = useMemo(() => ({
    compliant: composition?.checklist_counts.COMPLIANT || 0,
    noncompliant: composition?.checklist_counts.NONCOMPLIANT || 0,
    observations: composition?.checklist_counts.OBSERVATION || 0,
    notApplicable: composition?.checklist_counts.NOT_APPLICABLE || 0,
  }), [composition?.checklist_counts]);

  const download = async (artifact: GeneratedAuditReportArtifact) => {
    setDownloadBusy(artifact.id);
    setLocalError(null);
    try { saveDownloadedFile(await downloadGeneratedAuditReport(amoCode, auditId, artifact.id), artifact.filename); }
    catch (cause) { setLocalError(cause instanceof Error ? cause.message : "Generated report download failed."); }
    finally { setDownloadBusy(null); }
  };

  const registerPasskey = async () => {
    setCeremonyBusy("register"); setLocalError(null); setNotice(null);
    try {
      if (!isWebAuthnSupported() || !isSecureContextAvailable()) throw new Error("This browser or origin cannot perform a secure passkey ceremony.");
      const ceremony = await getAuditWebAuthnRegistrationOptions(amoCode);
      const credential = await createCredential(decodeCreationOptions(ceremony.options));
      if (!credential) throw new Error("Passkey registration was cancelled before a credential was created.");
      await verifyAuditWebAuthnRegistration(amoCode, ceremony.challenge_id, serializeRegistrationCredential(credential), passkeyNickname);
      setNotice("Passkey registered for governed Quality approvals.");
      await invalidateClosing();
    } catch (cause) { setLocalError(cause instanceof Error ? cause.message : "Passkey registration failed."); }
    finally { setCeremonyBusy(null); }
  };

  const signWithPasskey = async () => {
    if (!activeRevision || activeRevision.status !== "APPROVED") return;
    setCeremonyBusy("sign"); setLocalError(null); setNotice(null);
    try {
      if (!isWebAuthnSupported() || !isSecureContextAvailable()) throw new Error("This browser or origin cannot perform a secure passkey ceremony.");
      const ceremony = await getApprovedAuditReportSignatureOptions(amoCode, auditId, activeRevision.id);
      if (ceremony.already_signed && ceremony.signature) { setNotice("This exact approved report revision already has valid passkey evidence."); await invalidateClosing(); return; }
      if (!ceremony.challenge_id || !ceremony.options) throw new Error("The server did not return a complete report-signing challenge.");
      const assertion = await getAssertion(decodeRequestOptions(ceremony.options));
      if (!assertion) throw new Error("Passkey approval was cancelled before an assertion was returned.");
      await verifyApprovedAuditReportSignature(amoCode, auditId, activeRevision.id, ceremony.challenge_id, serializeAssertionCredential(assertion), signReason);
      setNotice("Passkey approval recorded against the exact approved report SHA-256. The report is now eligible for issue.");
      await invalidateClosing();
    } catch (cause) { setLocalError(cause instanceof Error ? cause.message : "Passkey report approval failed."); }
    finally { setCeremonyBusy(null); }
  };

  const createVerification = async () => {
    setCeremonyBusy("verify-link"); setLocalError(null);
    try {
      const token = await createAuditVerificationToken(amoCode, auditId, { assuranceArtifactId: currentAssuranceArtifact?.id || null });
      setVerificationUrl(new URL(token.verification_url, window.location.origin).toString());
      setNotice("A purpose-bound verification link was created. The raw token is shown only in this response and stored hashed by the server.");
    } catch (cause) { setLocalError(cause instanceof Error ? cause.message : "Verification link creation failed."); }
    finally { setCeremonyBusy(null); }
  };

  const refresh = async () => { setLocalError(null); await queryClient.invalidateQueries({ queryKey: ["qms-audit-output-policy", amoCode] }); await invalidateClosing(); };

  const loadError = auditQuery.error || compositionQuery.error || revisionsQuery.error || closureQuery.error || policyQuery.error || signaturesQuery.error || acknowledgementsQuery.error || assuranceArtifactsQuery.error || passkeysQuery.error;
  if (auditQuery.isLoading || compositionQuery.isLoading || revisionsQuery.isLoading || closureQuery.isLoading || policyQuery.isLoading || signaturesQuery.isLoading || acknowledgementsQuery.isLoading || assuranceArtifactsQuery.isLoading || (canManage && passkeysQuery.isLoading)) return <div className="qms-audit-closing qms-audit-closing--loading">Preparing governed closing meeting workspace…</div>;
  if (loadError || !auditQuery.data || !composition) return <div className="qms-audit-closing qms-audit-closing--loading" role="alert"><AlertTriangle size={20} /> {loadError instanceof Error ? loadError.message : "Closing workspace unavailable."}</div>;

  return (
    <div className="qms-audit-closing" role="region" aria-label="Audit closing meeting workspace">
      <header className="qms-audit-closing__header">
        <div><span>CLOSING MEETING · acknowledge → approve → passkey → issue</span><h1>{auditQuery.data.audit_ref} · {auditQuery.data.title}</h1></div>
        <div className="qms-audit-closing__header-actions"><button type="button" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</button><Link to={auditSessionPath(amoCode, auditKey, "live")}><X size={16} /> Exit closing</Link></div>
      </header>
      {localError ? <div className="qms-audit-closing__error" role="alert"><ShieldAlert size={16} /> {localError}</div> : null}
      {notice ? <div className="qms-audit-closing__success" role="status"><CheckCircle2 size={16} /> {notice}</div> : null}

      <div className="qms-audit-closing__body"><main>
        <section className="qms-audit-closing__card">
          <header><FileCheck2 size={19} /><div><strong>1 · Freeze fieldwork and generate the closing report</strong><small>The report is built from the authoritative audit, checklist, finding, CAR and preparation state.</small></div></header>
          <div className="qms-audit-closing__metrics"><div><strong>{counts.compliant}</strong><span>Compliant</span></div><div><strong>{counts.noncompliant}</strong><span>Noncompliant</span></div><div><strong>{counts.observations}</strong><span>Observations</span></div><div><strong>{composition.findings_count}</strong><span>Findings</span></div><div><strong>{composition.cars_count}</strong><span>CARs</span></div><div><strong>{pending}</strong><span>Not verified</span></div></div>
          {!composition.audit.actual_end ? <div className="qms-audit-closing__blocker"><AlertTriangle size={16} /> Fieldwork must be formally completed before a closing snapshot can be generated.</div> : null}
          {pending > 0 ? <div className="qms-audit-closing__blocker"><AlertTriangle size={16} /> {pending} checklist item(s) remain NOT_VERIFIED.</div> : null}
          <div className="qms-audit-closing__actions"><button type="button" className="is-primary" disabled={!canGenerate || generateMutation.isPending} onClick={() => generateMutation.mutate()}>{generateMutation.isPending ? "Generating…" : "Generate closing report draft"}</button>{latestGenerated ? <button type="button" onClick={() => void download(latestGenerated)} disabled={downloadBusy === latestGenerated.id}><Download size={15} /> {downloadBusy === latestGenerated.id ? "Downloading…" : "Preview / download"}</button> : null}{latestGenerated && !activeRevision ? <button type="button" disabled={!canManage || adoptMutation.isPending} onClick={() => adoptMutation.mutate(latestGenerated.id)}><FileSignature size={15} /> {adoptMutation.isPending ? "Adopting…" : "Adopt governed draft"}</button> : null}</div>
          {latestGenerated ? <dl className="qms-audit-closing__artifact"><div><dt>Artifact</dt><dd>{latestGenerated.filename}</dd></div><div><dt>Size</dt><dd>{bytes(latestGenerated.size_bytes)}</dd></div><div className="is-wide"><dt>Source snapshot SHA-256</dt><dd><code>{latestGenerated.source_snapshot_hash}</code></dd></div><div className="is-wide"><dt>Artifact SHA-256</dt><dd><code>{latestGenerated.sha256}</code></dd></div></dl> : <p className="qms-audit-closing__empty">No generated closing report exists yet.</p>}
        </section>

        <section className="qms-audit-closing__card">
          <header><FileSignature size={19} /><div><strong>2 · Auditee closing-meeting acknowledgement</strong><small>The response is bound to the exact governed draft and SHA-256 before internal review/approval.</small></div></header>
          {!currentRevision ? <p className="qms-audit-closing__empty">Adopt a governed draft before requesting acknowledgement.</p> : <><dl className="qms-audit-closing__artifact"><div><dt>Revision</dt><dd>R{currentRevision.revision_no} · {currentRevision.status.replaceAll("_", " ")}</dd></div><div className="is-wide"><dt>SHA-256</dt><dd><code>{currentRevision.sha256}</code></dd></div></dl>{currentAcknowledgement ? <div className="qms-audit-closing__success"><CheckCircle2 size={16} /><span><strong>{currentAcknowledgement.acknowledgement_status.replaceAll("_", " ")}</strong>{currentAcknowledgement.comments ? ` · ${currentAcknowledgement.comments}` : ""}</span></div> : currentRevision.status === "DRAFT" ? <div className="qms-audit-closing__blocker"><AlertTriangle size={16} /> The auditee workspace must record acknowledgement, comments, or declined acknowledgement against this exact draft before it can enter review when an auditee participant is assigned.</div> : <p className="qms-audit-closing__empty">No closing acknowledgement is attached to this revision.</p>}</>}
        </section>

        <section className="qms-audit-closing__card">
          <header><Stamp size={19} /><div><strong>3 · Review and Quality approval</strong><small>Approval does not issue the report. It creates the exact approved state that must then be authorized with a passkey.</small></div></header>
          {!activeRevision && issuedRevision ? <div className="qms-audit-closing__success"><CheckCircle2 size={16} /> Report R{issuedRevision.revision_no} is ISSUED.</div> : null}
          {activeRevision?.status === "DRAFT" ? <button type="button" className="is-primary" disabled={!canSubmit || transitionMutation.isPending} onClick={() => transitionMutation.mutate({ revision: activeRevision, action: "SUBMIT" })}>Submit acknowledged draft for review</button> : null}
          {activeRevision?.status === "INTERNAL_REVIEW" ? <div className="qms-audit-closing__actions"><button type="button" className="is-primary" disabled={!canApprove || transitionMutation.isPending} onClick={() => transitionMutation.mutate({ revision: activeRevision, action: "APPROVE" })}>Approve exact report revision</button><button type="button" disabled={transitionMutation.isPending} onClick={() => transitionMutation.mutate({ revision: activeRevision, action: "RETURN" })}>Return to draft</button></div> : null}
          {activeRevision?.status === "APPROVED" ? <div className="qms-audit-closing__success"><CheckCircle2 size={16} /> R{activeRevision.revision_no} is approved and locked to SHA-256 <code>{activeRevision.sha256}</code>.</div> : null}
        </section>

        <section className="qms-audit-closing__card">
          <header><Fingerprint size={19} /><div><strong>4 · Passkey signing ceremony</strong><small>WebAuthn user verification is recorded against the approved report revision/hash. Password re-auth is not treated as equivalent evidence.</small></div></header>
          {!isWebAuthnSupported() || !isSecureContextAvailable() ? <div className="qms-audit-closing__blocker"><AlertTriangle size={16} /> This browser/origin does not currently expose a secure WebAuthn context.</div> : null}
          {!passkeys.length ? <div className="qms-audit-closing__passkey-setup"><label><span>Passkey label</span><input value={passkeyNickname} onChange={(event) => setPasskeyNickname(event.target.value)} maxLength={80} /></label><button type="button" disabled={!canManage || ceremonyBusy !== null} onClick={() => void registerPasskey()}><KeyRound size={15} /> {ceremonyBusy === "register" ? "Registering…" : "Register passkey"}</button></div> : <p>{passkeys.length} active passkey{passkeys.length === 1 ? "" : "s"} registered for this Quality user.</p>}
          {activeRevision?.status === "APPROVED" && !currentSignature ? <div className="qms-audit-closing__passkey-sign"><label><span>Approval reason</span><textarea rows={3} value={signReason} onChange={(event) => setSignReason(event.target.value)} /></label><button type="button" className="is-primary" disabled={!canSign || !passkeys.length || ceremonyBusy !== null || signReason.trim().length < 8} onClick={() => void signWithPasskey()}><Fingerprint size={15} /> {ceremonyBusy === "sign" ? "Verifying passkey…" : "Approve exact report with passkey"}</button></div> : null}
          {currentSignature ? <dl className="qms-audit-closing__artifact"><div><dt>Method</dt><dd>{currentSignature.method}</dd></div><div><dt>Signed</dt><dd>{currentSignature.signed_at ? new Date(currentSignature.signed_at).toLocaleString() : "—"}</dd></div><div className="is-wide"><dt>Ceremony SHA-256</dt><dd><code>{currentSignature.ceremony_sha256 || currentSignature.signature_digest}</code></dd></div></dl> : null}
        </section>

        <section className="qms-audit-closing__card">
          <header><FileCheck2 size={19} /><div><strong>5 · Issue immutable report</strong><small>The server refuses ISSUE unless current passkey evidence matches the exact approved revision/hash and is newer than the approval state.</small></div></header>
          {activeRevision?.status === "APPROVED" ? <button type="button" className="is-primary" disabled={!canIssue || transitionMutation.isPending} onClick={() => transitionMutation.mutate({ revision: activeRevision, action: "ISSUE" })}>Issue passkey-approved report</button> : null}
          {issuedRevision ? <div className="qms-audit-closing__success"><CheckCircle2 size={16} /> Issued R{issuedRevision.revision_no} · {issuedRevision.issued_at ? new Date(issuedRevision.issued_at).toLocaleString() : "issued"}</div> : null}
        </section>

        <section className="qms-audit-closing__card">
          <header><ShieldAlert size={19} /><div><strong>6 · Close execution without erasing follow-up</strong><small>Execution closure and CAR/CAPA completion are separate controls.</small></div></header>
          {closure?.execution_readiness.blockers?.length ? <ul>{closure.execution_readiness.blockers.map((blocker, index) => <li key={`${blocker.type}-${index}`}>{blocker.reason}</li>)}</ul> : null}
          <button type="button" disabled={!canExecutionClose || executionCloseMutation.isPending} onClick={() => executionCloseMutation.mutate()}>{executionCloseMutation.isPending ? "Closing execution…" : closure?.execution_status === "CLOSED" ? "Execution closed" : "Close audit execution"}</button>
        </section>

        <section className="qms-audit-closing__card">
          <header><Stamp size={19} /><div><strong>7 · Policy-controlled assurance output and verification</strong><small>Certificate/approval output is generated only when policy requires it. Verification tokens are high-entropy and stored only as hashes.</small></div></header>
          <p>Output policy: <strong>{policy?.artifact_policy || "Not configured"}</strong>{policy?.rationale ? ` · ${policy.rationale}` : ""}</p>
          {canGenerateAssurance && currentSignature ? <button type="button" disabled={assuranceArtifactMutation.isPending} onClick={() => assuranceArtifactMutation.mutate(currentSignature.id)}>{assuranceArtifactMutation.isPending ? "Generating…" : `Generate ${policy?.artifact_policy.replaceAll("_", " ")}`}</button> : null}
          {currentAssuranceArtifact ? <dl className="qms-audit-closing__artifact"><div><dt>Artifact</dt><dd>{currentAssuranceArtifact.filename}</dd></div><div><dt>Type</dt><dd>{currentAssuranceArtifact.artifact_type.replaceAll("_", " ")}</dd></div><div className="is-wide"><dt>SHA-256</dt><dd><code>{currentAssuranceArtifact.sha256}</code></dd></div></dl> : null}
          {issuedRevision && currentSignature ? <button type="button" disabled={ceremonyBusy !== null} onClick={() => void createVerification()}><ExternalLink size={15} /> {ceremonyBusy === "verify-link" ? "Creating…" : "Create public verification link"}</button> : null}
          {verificationUrl ? <div className="qms-audit-closing__verification"><strong>Verification URL</strong><a href={verificationUrl} target="_blank" rel="noreferrer">{verificationUrl}</a></div> : null}
        </section>
      </main></div>
    </div>
  );
};

export default AuditClosingWorkspace;
