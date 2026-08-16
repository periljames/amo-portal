import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Download,
  FileCheck2,
  FileSignature,
  RefreshCw,
  ShieldAlert,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { qmsResolveAudit } from "../../../services/qms";
import {
  getAuditClosureState,
  listAuditReportRevisions,
} from "../../../services/qmsAuditCloseout";
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

function bytes(value: number): string {
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${Math.round(value / 1024)} KB`;
  return `${value} B`;
}

const AuditClosingWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [downloadBusy, setDownloadBusy] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

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

  const generateMutation = useMutation({
    mutationFn: () => generateAuditClosingReport(amoCode, auditId),
    onSuccess: async () => {
      setLocalError(null);
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-report-composition", amoCode, auditId] });
    },
    onError: (cause) => setLocalError(cause instanceof Error ? cause.message : "Closing report generation failed."),
  });

  const composition = compositionQuery.data;
  const pending = composition?.checklist_counts.NOT_VERIFIED || 0;
  const latestGenerated = composition?.artifacts[0] || null;
  const latestRevision = revisionsQuery.data?.items?.[0] || null;
  const issuedRevision = revisionsQuery.data?.items?.find((revision) => revision.status === "ISSUED") || null;
  const closure = closureQuery.data;
  const canGenerate = Boolean(canManage && composition?.audit.actual_end && pending === 0);

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
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-report-composition", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-report-revisions", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-closure-state", amoCode, auditId] }),
    ]);
  };

  const loadError = auditQuery.error || compositionQuery.error || revisionsQuery.error || closureQuery.error;
  if (auditQuery.isLoading || compositionQuery.isLoading || revisionsQuery.isLoading || closureQuery.isLoading) {
    return <div className="qms-audit-closing qms-audit-closing--loading">Preparing closing meeting workspace…</div>;
  }
  if (loadError || !auditQuery.data || !composition) {
    return <div className="qms-audit-closing qms-audit-closing--loading" role="alert"><AlertTriangle size={20} /> {loadError instanceof Error ? loadError.message : "Closing workspace unavailable."}</div>;
  }

  return (
    <div className="qms-audit-closing" role="region" aria-label="Audit closing meeting workspace">
      <header className="qms-audit-closing__header">
        <div><span>CLOSING MEETING · controlled report handoff</span><h1>{auditQuery.data.audit_ref} · {auditQuery.data.title}</h1></div>
        <div className="qms-audit-closing__header-actions"><button type="button" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</button><Link to={auditSessionPath(amoCode, auditKey, "live")}><X size={16} /> Exit closing</Link></div>
      </header>

      {localError ? <div className="qms-audit-closing__error" role="alert"><ShieldAlert size={16} /> {localError}</div> : null}

      <div className="qms-audit-closing__body">
        <main>
          <section className="qms-audit-closing__card">
            <header><FileCheck2 size={19} /><div><strong>Frozen closing report draft</strong><small>Generated from authoritative audit, checklist, finding, CAR and preparation data.</small></div></header>
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
            <header><FileSignature size={19} /><div><strong>Governed report lifecycle</strong><small>The generated PDF is not an issued report by itself.</small></div></header>
            <div className="qms-audit-closing__lifecycle">
              <div><span>Generated artifact</span><strong>{latestGenerated ? "READY" : "PENDING"}</strong></div>
              <ArrowRight size={16} />
              <div><span>Governed revision</span><strong>{latestRevision ? `Rev ${latestRevision.revision_no} · ${latestRevision.status}` : "PENDING"}</strong></div>
              <ArrowRight size={16} />
              <div><span>Issued</span><strong>{issuedRevision ? `Rev ${issuedRevision.revision_no}` : "PENDING"}</strong></div>
            </div>
            <p>The current report governance still owns internal review, approval, issue and supersession. Automatic adoption of this generated artifact into that revision lifecycle is not yet enabled on this branch; it will be wired without weakening the existing gates.</p>
          </section>
        </main>

        <aside>
          <section className="qms-audit-closing__card qms-audit-closing__gates">
            <header><CheckCircle2 size={19} /><div><strong>Closing gates</strong><small>Authoritative backend readiness.</small></div></header>
            <ul>
              <li data-ready={Boolean(composition.audit.actual_end)}><span>Fieldwork completed</span><strong>{composition.audit.actual_end ? "Ready" : "Blocked"}</strong></li>
              <li data-ready={pending === 0}><span>Checklist resolved</span><strong>{pending === 0 ? "Ready" : `${pending} pending`}</strong></li>
              <li data-ready={Boolean(issuedRevision)}><span>Issued report revision</span><strong>{issuedRevision ? "Ready" : "Pending"}</strong></li>
              <li data-ready={closure?.execution_readiness.ready === true}><span>Execution close readiness</span><strong>{closure?.execution_readiness.ready ? "Ready" : `${closure?.execution_readiness.blockers.length || 0} blocker(s)`}</strong></li>
            </ul>
          </section>

          <section className="qms-audit-closing__card qms-audit-closing__signature">
            <header><FileSignature size={19} /><div><strong>Electronic signature</strong><small>Not yet integrated.</small></div></header>
            <p>The historical e-signature PR is being treated as reusable source material only. This workspace will not show a false “signed” state until passkey/signature evidence is ported and verified against current main.</p>
          </section>

          <Link className="qms-audit-closing__continue" to={auditSessionPath(amoCode, auditKey, "follow-up")}>Open Follow-up <ArrowRight size={16} /></Link>
        </aside>
      </div>
    </div>
  );
};

export default AuditClosingWorkspace;
