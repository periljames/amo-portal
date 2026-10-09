import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  Download,
  FileLock2,
  RefreshCw,
  Scale,
  ShieldCheck,
  Trash2,
  Unlock,
} from "lucide-react";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import {
  createAuditRetentionPolicyRevision,
  downloadAuditArchivePackage,
  executeAuditDisposition,
  generateAuditArchiveManifest,
  getAuditArchiveGovernance,
  placeAuditLegalHold,
  releaseAuditLegalHold,
  reviewAuditDisposition,
  type AuditDispositionMode,
  type AuditRetentionStart,
} from "../../../services/qmsAuditArchiveGovernance";
import { auditOccurrenceQueryKey, resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";
import { saveDownloadedFile } from "../../../utils/downloads";
import { AuditStageLoadError } from "./AuditStageLoadError";
import { auditOccurrenceLoadDetail, auditPrerequisiteLoadDetail } from "./auditStageLoadErrorMessages";
import { auditSessionPath } from "./auditSessionRoutes";
import "../../../styles/qms-audit-archive-workspace.css";

type Props = { amoCode: string; auditKey: string };

type PolicyForm = {
  retentionClass: string;
  retentionStart: AuditRetentionStart;
  durationDays: string;
  indefinite: boolean;
  governingBasis: string;
  reviewBeforeDisposition: boolean;
  legalHoldSupported: boolean;
  dispositionMode: AuditDispositionMode;
  approvingCapability: string;
};

const emptyPolicy: PolicyForm = {
  retentionClass: "",
  retentionStart: "FOLLOW_UP_COMPLETE",
  durationDays: "",
  indefinite: false,
  governingBasis: "",
  reviewBeforeDisposition: true,
  legalHoldSupported: true,
  dispositionMode: "NO_DISPOSITION",
  approvingCapability: "qms.audit.manage",
};

function readableBytes(value?: number | null): string {
  if (!value) return "—";
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${Math.round(value / 1024)} KB`;
  return `${value} B`;
}

function dateTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

const AuditArchiveWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [policyForm, setPolicyForm] = useState<PolicyForm>(emptyPolicy);
  const [holdKey, setHoldKey] = useState("");
  const [holdReason, setHoldReason] = useState("");
  const [holdBasis, setHoldBasis] = useState("");
  const [holdRelease, setHoldRelease] = useState<{ key: string; reason: string; basis: string } | null>(null);
  const [reviewReason, setReviewReason] = useState("");
  const [disposeReason, setDisposeReason] = useState("");
  const [disposeConfirmation, setDisposeConfirmation] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [downloadBusy, setDownloadBusy] = useState(false);

  const auditQuery = useQuery({
    queryKey: auditOccurrenceQueryKey(amoCode, auditKey),
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const governanceQuery = useQuery({
    queryKey: ["qms-audit-archive-governance", amoCode, auditId],
    queryFn: ({ signal }) => getAuditArchiveGovernance(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 1_500,
  });

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-archive-governance", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "audit-session", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: auditOccurrenceQueryKey(amoCode, auditKey) }),
    ]);
  };
  const success = async (message: string) => {
    setLocalError(null);
    setNotice(message);
    await invalidate();
  };
  const failure = (cause: unknown, fallback: string) => {
    setNotice(null);
    setLocalError(cause instanceof Error ? cause.message : fallback);
  };

  const policyMutation = useMutation({
    mutationFn: () => createAuditRetentionPolicyRevision(amoCode, {
      retention_class: policyForm.retentionClass.trim(),
      retention_start_event: policyForm.retentionStart,
      duration_days: policyForm.indefinite ? null : Number(policyForm.durationDays),
      indefinite: policyForm.indefinite,
      governing_basis: policyForm.governingBasis.trim(),
      review_before_disposition: policyForm.reviewBeforeDisposition,
      legal_hold_supported: policyForm.legalHoldSupported,
      disposition_mode: policyForm.indefinite ? "NO_DISPOSITION" : policyForm.dispositionMode,
      approving_capability: policyForm.approvingCapability.trim(),
    }),
    onSuccess: () => void success("Retention policy revision recorded."),
    onError: (cause) => failure(cause, "Retention policy update failed."),
  });
  const manifestMutation = useMutation({
    mutationFn: () => generateAuditArchiveManifest(amoCode, auditId),
    onSuccess: () => void success("Immutable archive manifest and package generated."),
    onError: (cause) => failure(cause, "Archive package generation failed."),
  });
  const holdMutation = useMutation({
    mutationFn: () => placeAuditLegalHold(amoCode, auditId, holdKey.trim(), {
      reason: holdReason.trim(),
      governing_basis: holdBasis.trim(),
      manifest_id: governanceQuery.data?.manifest?.id || null,
    }),
    onSuccess: () => {
      setHoldKey(""); setHoldReason(""); setHoldBasis("");
      void success("Legal hold placed. Disposition is blocked until controlled release.");
    },
    onError: (cause) => failure(cause, "Legal hold placement failed."),
  });
  const releaseMutation = useMutation({
    mutationFn: () => {
      if (!holdRelease) throw new Error("Select the legal hold and provide its release authority.");
      return releaseAuditLegalHold(amoCode, auditId, holdRelease.key, {
        reason: holdRelease.reason.trim(),
        governing_basis: holdRelease.basis.trim(),
        manifest_id: governanceQuery.data?.manifest?.id || null,
      });
    },
    onSuccess: () => { setHoldRelease(null); void success("Legal hold released and its reason and authority recorded."); },
    onError: (cause) => failure(cause, "Legal hold release failed."),
  });
  const reviewMutation = useMutation({
    mutationFn: (approved: boolean) => reviewAuditDisposition(amoCode, auditId, governanceQuery.data?.manifest?.id || "", approved, reviewReason.trim()),
    onSuccess: (row) => void success(`Disposition review ${row.event_type.toLowerCase()}.`),
    onError: (cause) => failure(cause, "Disposition review failed."),
  });
  const disposeMutation = useMutation({
    mutationFn: () => executeAuditDisposition(amoCode, auditId, governanceQuery.data?.manifest?.id || "", disposeReason.trim()),
    onSuccess: () => void success("Disposition executed. Governed metadata and evidence of the action remain retained."),
    onError: (cause) => failure(cause, "Disposition execution failed."),
  });

  const governance = governanceQuery.data;
  const policy = governance?.policy?.current || null;
  const manifest = governance?.manifest || null;
  const expectedConfirmation = auditQuery.data ? `DISPOSE ${auditQuery.data.audit_ref}` : "";
  const policyFormValid = policyForm.retentionClass.trim().length >= 2
    && policyForm.governingBasis.trim().length >= 8
    && policyForm.approvingCapability.trim().length >= 3
    && (policyForm.indefinite || (Number.isSafeInteger(Number(policyForm.durationDays)) && Number(policyForm.durationDays) > 0));
  const holdFormValid = holdKey.trim().length > 0 && holdReason.trim().length >= 8 && holdBasis.trim().length >= 8;
  const canDispose = Boolean(
    canManage
    && manifest
    && manifest.package_available !== false
    && policy
    && governance?.retention_due
    && governance.active_holds.length === 0
    && policy.disposition_mode !== "NO_DISPOSITION"
    && !policy.indefinite
    && governance.disposition?.event_type !== "EXECUTED"
    && (!policy.review_before_disposition || governance.disposition_review_valid === true)
    && disposeReason.trim().length >= 8
    && disposeConfirmation.trim() === expectedConfirmation,
  );

  const itemGroups = useMemo(() => {
    const groups = new Map<string, number>();
    for (const item of manifest?.items || []) groups.set(item.item_type, (groups.get(item.item_type) || 0) + 1);
    return Array.from(groups.entries()).sort(([left], [right]) => left.localeCompare(right));
  }, [manifest?.items]);

  const download = async () => {
    if (!manifest) return;
    setDownloadBusy(true); setLocalError(null);
    try {
      const blob = await downloadAuditArchivePackage(amoCode, auditId, manifest.id);
      saveDownloadedFile(blob, manifest.package_filename || `${auditQuery.data?.audit_ref || auditId}-archive.zip`);
    } catch (cause) {
      failure(cause, "Archive package download failed.");
    } finally {
      setDownloadBusy(false);
    }
  };

  if (auditQuery.isPending || (Boolean(auditId) && governanceQuery.isPending)) return <div className="qms-audit-archive qms-audit-archive--loading">Loading governed audit archive…</div>;
  if (auditQuery.error || !auditQuery.data) {
    return (
      <AuditStageLoadError
        className="qms-audit-archive qms-audit-archive--error"
        title="Audit occurrence unavailable"
        detail={auditOccurrenceLoadDetail(auditQuery.error)}
        onRetry={() => void auditQuery.refetch()}
        exitHref={auditSessionPath(amoCode, auditKey, "follow-up")}
        exitLabel="Back to Follow-up"
        secondaryHref={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits`}
        secondaryLabel="Audits overview"
      />
    );
  }
  if (governanceQuery.error || !governance) {
    return (
      <AuditStageLoadError
        className="qms-audit-archive qms-audit-archive--error"
        title="Complete follow-up before archiving"
        detail={auditPrerequisiteLoadDetail(
          governanceQuery.error,
          "Archive governance is not initialized yet. Complete the required follow-up and closeout actions before opening Archive.",
        )}
        onRetry={() => void governanceQuery.refetch()}
        exitHref={auditSessionPath(amoCode, auditKey, "follow-up")}
        exitLabel="Back to Follow-up"
        secondaryHref={auditSessionPath(amoCode, auditKey, "setup")}
        secondaryLabel="Open Setup"
      />
    );
  }

  return (
    <section className="qms-audit-archive" aria-label="Audit archive and retention workspace">
      <header className="qms-audit-archive__header">
        <div><span>Archive</span><h2>Retention and disposition</h2></div>
        <button type="button" onClick={() => void invalidate()}><RefreshCw size={15} /> Refresh</button>
      </header>
      {localError ? <div className="qms-audit-archive__message is-error" role="alert"><AlertTriangle size={16} /> {localError}</div> : null}
      {notice ? <div className="qms-audit-archive__message" role="status"><CheckCircle2 size={16} /> {notice}</div> : null}
      {!governance.archive_readiness?.ready ? <div className="qms-audit-archive__blocker" role="status"><AlertTriangle size={16} /><div><strong>Archive generation is locked</strong><ul>{governance.archive_readiness?.blockers.map((blocker, index) => <li key={`${blocker.type}-${index}`}>{blocker.reason}</li>) || <li>Refresh to verify archive readiness.</li>}</ul><a href={auditSessionPath(amoCode, auditKey, "follow-up")}>Review follow-up requirements</a></div></div> : null}

      <div className="qms-audit-archive__grid">
        <main>
          <article className="qms-audit-archive__card">
            <header><Archive size={19} /><div><strong>Immutable audit package</strong><small>Authoritative record references and hashes are frozen into a versioned manifest.</small></div></header>
            {!policy ? <div className="qms-audit-archive__blocker"><AlertTriangle size={16} /> Configure a governed retention policy before generating an archive.</div> : null}
            {manifest ? (
              <>
                <dl className="qms-audit-archive__facts">
                  <div><dt>Manifest</dt><dd>v{manifest.manifest_version}</dd></div>
                  <div><dt>Records</dt><dd>{manifest.item_count}</dd></div>
                  <div><dt>Retention class</dt><dd>{manifest.retention_class}</dd></div>
                  <div><dt>Retention due</dt><dd>{manifest.retention_due_at ? dateTime(manifest.retention_due_at) : "Indefinite"}</dd></div>
                  <div><dt>Package</dt><dd>{manifest.package_filename || "Structured manifest retained"}</dd></div>
                  <div><dt>Package size</dt><dd>{readableBytes(manifest.package_size_bytes)}</dd></div>
                  
                  
                </dl>
                <div className="qms-audit-archive__groups">{itemGroups.map(([type, count]) => <span key={type}>{type.replaceAll("_", " ")} · {count}</span>)}</div>
                <div className="qms-audit-archive__actions">
                  {manifest.package_filename ? <button type="button" onClick={() => void download()} disabled={downloadBusy || manifest.package_available === false}><Download size={15} /> {downloadBusy ? "Downloading…" : "Download verified package"}</button> : null}
                  {canManage ? <button type="button" onClick={() => manifestMutation.mutate()} disabled={!governance.archive_readiness?.ready || manifestMutation.isPending}>{manifestMutation.isPending ? "Generating…" : "Generate new manifest version"}</button> : null}
                </div>
              </>
            ) : (
              <div className="qms-audit-archive__empty"><p>No archive manifest exists for this audit.</p>{canManage ? <button type="button" disabled={!governance.archive_readiness?.ready || manifestMutation.isPending} onClick={() => manifestMutation.mutate()}>{manifestMutation.isPending ? "Generating…" : "Generate governed archive"}</button> : null}</div>
            )}
          </article>

          <article className="qms-audit-archive__card">
            <header><FileLock2 size={19} /><div><strong>Legal holds</strong><small>Active holds block disposition regardless of retention due date.</small></div></header>
            {governance.active_holds.length ? <div className="qms-audit-archive__holds">{governance.active_holds.map((hold) => <div key={hold.hold_key}><div><strong>{hold.hold_key}</strong><span>{hold.reason}</span><small>{hold.governing_basis} · {dateTime(hold.created_at)}</small></div>{canManage ? <button type="button" onClick={() => setHoldRelease({ key: hold.hold_key, reason: "", basis: "" })} disabled={releaseMutation.isPending}><Unlock size={14} /> Release</button> : null}</div>)}</div> : <p className="qms-audit-archive__empty">No active legal holds.</p>}
            {holdRelease ? <div className="qms-audit-archive__hold-form" role="group" aria-label={`Release legal hold ${holdRelease.key}`}>
              <strong>Release hold {holdRelease.key}</strong>
              <label><span>Release reason</span><textarea rows={3} value={holdRelease.reason} onChange={(event) => setHoldRelease((current) => current ? { ...current, reason: event.target.value } : null)} /></label>
              <label><span>Authority / governing basis for release</span><textarea rows={3} value={holdRelease.basis} onChange={(event) => setHoldRelease((current) => current ? { ...current, basis: event.target.value } : null)} /></label>
              <p>Releasing this hold removes its disposition block. Record the authority that permits the release.</p>
              <button type="button" disabled={releaseMutation.isPending} onClick={() => setHoldRelease(null)}>Cancel</button>
              <button type="button" disabled={holdRelease.reason.trim().length < 8 || holdRelease.basis.trim().length < 8 || releaseMutation.isPending} onClick={() => releaseMutation.mutate()}>{releaseMutation.isPending ? "Releasing…" : "Confirm hold release"}</button>
            </div> : null}
            {canManage && policy?.legal_hold_supported ? <div className="qms-audit-archive__hold-form"><input value={holdKey} onChange={(event) => setHoldKey(event.target.value)} placeholder="Hold reference / case number" aria-label="Legal hold reference" /><textarea rows={2} value={holdReason} onChange={(event) => setHoldReason(event.target.value)} placeholder="Reason for hold" aria-label="Legal hold reason" /><textarea rows={2} value={holdBasis} onChange={(event) => setHoldBasis(event.target.value)} placeholder="Governing basis / authority" aria-label="Legal hold governing basis" /><button type="button" disabled={!holdFormValid || holdMutation.isPending} onClick={() => holdMutation.mutate()}><FileLock2 size={14} /> Place legal hold</button></div> : null}
          </article>
        </main>

        <aside>
          <article className="qms-audit-archive__card">
            <header><ShieldCheck size={19} /><div><strong>Retention policy</strong><small>Tenant configuration; duration is never hard-coded by the application.</small></div></header>
            {policy ? <dl className="qms-audit-archive__policy"><div><dt>Revision</dt><dd>{policy.revision_no}</dd></div><div><dt>Class</dt><dd>{policy.retention_class}</dd></div><div><dt>Starts</dt><dd>{policy.retention_start_event.replaceAll("_", " ")}</dd></div><div><dt>Duration</dt><dd>{policy.indefinite ? "Indefinite" : `${policy.duration_days} days`}</dd></div><div><dt>Disposition</dt><dd>{policy.disposition_mode.replaceAll("_", " ")}</dd></div><div><dt>Approval</dt><dd>{policy.approving_capability}</dd></div><div className="is-wide"><dt>Basis</dt><dd>{policy.governing_basis}</dd></div></dl> : <p className="qms-audit-archive__empty">No retention policy has been configured.</p>}
            {canManage ? <details className="qms-audit-archive__policy-editor"><summary>{policy ? "Create policy revision" : "Configure retention policy"}</summary><label><span>Retention class</span><input value={policyForm.retentionClass} onChange={(event) => setPolicyForm((current) => ({ ...current, retentionClass: event.target.value }))} /></label><label><span>Retention starts at</span><select value={policyForm.retentionStart} onChange={(event) => setPolicyForm((current) => ({ ...current, retentionStart: event.target.value as AuditRetentionStart }))}><option value="FOLLOW_UP_COMPLETE">Assurance follow-up complete</option><option value="EXECUTION_CLOSED">Audit execution closed</option></select></label><label className="is-check"><input type="checkbox" checked={policyForm.indefinite} onChange={(event) => setPolicyForm((current) => ({ ...current, indefinite: event.target.checked, dispositionMode: event.target.checked ? "NO_DISPOSITION" : current.dispositionMode }))} /><span>Retain indefinitely</span></label>{!policyForm.indefinite ? <label><span>Duration · days</span><input type="number" min={1} value={policyForm.durationDays} onChange={(event) => setPolicyForm((current) => ({ ...current, durationDays: event.target.value }))} /></label> : null}<label><span>Disposition mode</span><select disabled={policyForm.indefinite} value={policyForm.indefinite ? "NO_DISPOSITION" : policyForm.dispositionMode} onChange={(event) => setPolicyForm((current) => ({ ...current, dispositionMode: event.target.value as AuditDispositionMode }))}><option value="NO_DISPOSITION">No disposition</option><option value="PRESERVE_METADATA_DELETE_PACKAGE">Delete package; preserve disposition metadata</option><option value="TRANSFER_PACKAGE">Transfer package to controlled archive</option></select></label><label><span>Approving capability</span><input value={policyForm.approvingCapability} onChange={(event) => setPolicyForm((current) => ({ ...current, approvingCapability: event.target.value }))} /></label><label className="is-check"><input type="checkbox" checked={policyForm.reviewBeforeDisposition} onChange={(event) => setPolicyForm((current) => ({ ...current, reviewBeforeDisposition: event.target.checked }))} /><span>Require disposition review</span></label><label className="is-check"><input type="checkbox" checked={policyForm.legalHoldSupported} onChange={(event) => setPolicyForm((current) => ({ ...current, legalHoldSupported: event.target.checked }))} /><span>Enable legal holds</span></label><label><span>Governing basis</span><textarea rows={3} value={policyForm.governingBasis} onChange={(event) => setPolicyForm((current) => ({ ...current, governingBasis: event.target.value }))} /></label><button type="button" disabled={!policyFormValid || policyMutation.isPending} onClick={() => policyMutation.mutate()}>{policyMutation.isPending ? "Recording…" : "Record immutable policy revision"}</button></details> : null}
          </article>

          <article className="qms-audit-archive__card">
            <header><Scale size={19} /><div><strong>Disposition control</strong><small>Due date, hold state, approval and exact inventory are enforced server-side.</small></div></header>
            <ul className="qms-audit-archive__gates"><li data-ready={Boolean(manifest)}><span>Archive manifest</span><strong>{manifest ? "Ready" : "Missing"}</strong></li><li data-ready={governance.retention_due}><span>Retention due</span><strong>{governance.retention_due ? "Due" : "Not due"}</strong></li><li data-ready={governance.active_holds.length === 0}><span>No active hold</span><strong>{governance.active_holds.length ? `${governance.active_holds.length} hold(s)` : "Clear"}</strong></li><li data-ready={!policy?.review_before_disposition || governance.disposition_review_valid === true}><span>Disposition review</span><strong>{!policy?.review_before_disposition ? "Not required by policy" : governance.disposition_review_valid ? "Approved for this package" : governance.disposition?.event_type === "EXECUTED" ? "Executed" : "Review required"}</strong></li></ul>
            {governance.disposition ? <p className="qms-audit-archive__disposition-state"><strong>{governance.disposition.event_type}</strong> · {governance.disposition.reason}</p> : null}
            {canManage && manifest && policy && policy.disposition_mode !== "NO_DISPOSITION" ? <div className="qms-audit-archive__disposition"><textarea rows={2} value={reviewReason} onChange={(event) => setReviewReason(event.target.value)} placeholder="Disposition review rationale" aria-label="Disposition review rationale" /><div><button type="button" disabled={reviewReason.trim().length < 8 || reviewMutation.isPending || governance.disposition?.event_type === "EXECUTED"} onClick={() => reviewMutation.mutate(true)}><CheckCircle2 size={14} /> Approve review</button><button type="button" disabled={reviewReason.trim().length < 8 || reviewMutation.isPending || governance.disposition?.event_type === "EXECUTED"} onClick={() => reviewMutation.mutate(false)}><AlertTriangle size={14} /> Reject</button></div><textarea rows={2} value={disposeReason} onChange={(event) => setDisposeReason(event.target.value)} placeholder="Execution rationale" aria-label="Disposition execution rationale" /><label><span>Type <code>{expectedConfirmation}</code> to execute</span><input value={disposeConfirmation} onChange={(event) => setDisposeConfirmation(event.target.value)} /></label><button className="is-danger" type="button" disabled={!canDispose || disposeMutation.isPending} onClick={() => disposeMutation.mutate()}><Trash2 size={14} /> {disposeMutation.isPending ? "Executing…" : "Execute disposition"}</button></div> : <p className="qms-audit-archive__empty">Current policy does not permit disposition, or no package exists.</p>}
          </article>
        </aside>
      </div>
    </section>
  );
};

export default AuditArchiveWorkspace;
