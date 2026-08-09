import React, { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BookOpenCheck, ClipboardList, History, Link2, PanelRightClose, PanelRightOpen, RefreshCw, ShieldCheck } from "lucide-react";

import { qmsResolveAudit } from "../../services/qms";
import { getAuditPreparationContext } from "../../services/qmsAuditPreparationContext";
import "../../styles/qms-audit-preparation-context.css";

type Props = { amoCode: string; auditKey: string };

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  try { return JSON.stringify(value); } catch { return String(value); }
}

const QualityAuditPreparationContextHost: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const auditQuery = useQuery({
    queryKey: ["qms-preparation-context-resolve", auditKey],
    queryFn: () => qmsResolveAudit(auditKey),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const contextQuery = useQuery({
    queryKey: ["qms-audit-preparation-context", amoCode, auditId],
    queryFn: ({ signal }) => getAuditPreparationContext(amoCode, auditId, signal),
    enabled: Boolean(open && auditId),
  });
  const context = contextQuery.data;
  const topFindings = useMemo(() => context?.prior_findings.items.slice(0, 12) || [], [context]);
  const topAudits = useMemo(() => context?.prior_audit_history.items.slice(0, 8) || [], [context]);

  if (!auditQuery.data) return null;

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["qms-audit-preparation-context", amoCode, auditId] });
  };

  return <>
    <button className="qms-audit-preparation-context-launcher" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="qms-audit-preparation-context-panel">
      {open ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />} Preparation intelligence
    </button>
    {open ? <aside id="qms-audit-preparation-context-panel" className="qms-audit-preparation-context-panel" aria-label="Source-backed audit preparation context">
      <header>
        <div><span>Prepare with evidence</span><strong>{auditQuery.data.audit_ref} · Preparation intelligence</strong></div>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close preparation intelligence"><PanelRightClose size={18} /></button>
      </header>
      <div className="qms-audit-preparation-context-body">
        {contextQuery.isLoading ? <p>Loading authoritative preparation context…</p> : null}
        {contextQuery.error ? <div className="qms-audit-preparation-context-error" role="alert"><AlertTriangle size={16} />{contextQuery.error instanceof Error ? contextQuery.error.message : "Preparation context could not be loaded."}</div> : null}
        {context ? <>
          <section className="qms-audit-preparation-context-summary">
            <article><strong>{context.prior_audit_history.items.length}</strong><span>Prior related audits</span></article>
            <article><strong>{context.prior_findings.total}</strong><span>Prior findings</span></article>
            <article><strong>{context.car_exposure.open_count}</strong><span>Open CAR exposure</span></article>
            <article><strong>{context.cross_source_assurance_pressure.factors.length}</strong><span>AMO pressure factors</span></article>
          </section>

          <section className="qms-audit-preparation-context-card">
            <header><History size={17} /><strong>Prior audit history</strong><span>{context.prior_audit_history.matching_basis}</span></header>
            {topAudits.length ? <ol>{topAudits.map((row) => <li key={row.id}><strong>{row.audit_ref} · {row.title}</strong><span>{row.status || "UNKNOWN"} · {row.actual_end || row.planned_end || "date unavailable"}</span><small>{row.scope || "No recorded scope summary."}</small></li>)}</ol> : <p>No related prior audits were found for the governed scope/kind.</p>}
          </section>

          <section className="qms-audit-preparation-context-card">
            <header><ClipboardList size={17} /><strong>Recurring finding / CAR exposure</strong><span>{context.car_exposure.open_count} open CAR(s)</span></header>
            {Object.keys(context.prior_findings.classification_counts).length ? <div className="qms-audit-preparation-context-tags">{Object.entries(context.prior_findings.classification_counts).map(([key, count]) => <span key={key}>{key}: {count}</span>)}</div> : null}
            {topFindings.length ? <ol>{topFindings.map((row) => <li key={row.id}><strong>{row.finding_ref || "Finding"} · {row.classification || row.severity || "UNCLASSIFIED"}</strong><span>{row.status || (row.closed_at ? "CLOSED" : "OPEN")}</span><small>{row.title || row.description || row.requirement_ref || "No finding summary."}</small></li>)}</ol> : <p>No prior findings were found for related audits.</p>}
          </section>

          <section className="qms-audit-preparation-context-card">
            <header><ShieldCheck size={17} /><strong>Cross-source assurance pressure</strong><span>context, not conclusion</span></header>
            <p>{context.cross_source_assurance_pressure.statement}</p>
            {context.cross_source_assurance_pressure.factors.length ? <div className="qms-audit-preparation-context-factors">{context.cross_source_assurance_pressure.factors.map((factor) => <article key={factor.code}><strong>{factor.label}</strong><span>{display(factor.value)} · {factor.source}</span><small>{factor.rationale}</small></article>)}</div> : <p>No attributable AMO-level pressure factor is currently raised.</p>}
          </section>

          <section className="qms-audit-preparation-context-card">
            <header><BookOpenCheck size={17} /><strong>Controlled basis & preparation state</strong><span>{context.controlled_preparation.latest_revision ? `Prep Rev ${context.controlled_preparation.latest_revision.revision_no}` : "No issued prep revision"}</span></header>
            <dl><div><dt>Audit scope</dt><dd>{context.regulatory_and_manual_basis.audit_scope || "—"}</dd></div><div><dt>Audit criteria</dt><dd>{context.regulatory_and_manual_basis.audit_criteria || "—"}</dd></div><div><dt>Document requests</dt><dd>{context.document_requests.length}</dd></div><div><dt>Opening-meeting records</dt><dd>{context.opening_meeting_records.length}</dd></div><div><dt>Checklist bindings</dt><dd>{context.controlled_preparation.checklist_bindings.length}</dd></div></dl>
            {context.controlled_preparation.checklist_bindings.length ? <ul>{context.controlled_preparation.checklist_bindings.map((row) => <li key={row.id}><strong>{row.template_code} Rev {row.revision_no}</strong><span>SHA {row.content_sha256.slice(0, 14)}…</span><small>{row.application_reason}</small></li>)}</ul> : null}
          </section>

          <section className="qms-audit-preparation-context-card">
            <header><Link2 size={17} /><strong>Mission / signal / schedule lineage</strong><span>{context.source_lineage.items.length} source link(s)</span></header>
            {context.source_lineage.items.length ? <ul>{context.source_lineage.items.map((row, index) => <li key={`${row.source_type}-${row.source_id}-${index}`}><strong>{row.source_type} · {row.source_id}</strong><small>{row.rationale}</small>{row.source_route ? <a href={row.source_route}>Open authoritative source</a> : null}</li>)}</ul> : <p>No Mission/Signal/Assurance source lineage is attached to this audit occurrence.</p>}
          </section>

          {context.data_quality.warnings.length ? <section className="qms-audit-preparation-context-card is-warning"><header><AlertTriangle size={17} /><strong>Source/data warnings</strong><span>{context.data_quality.warnings.length}</span></header><p>{context.data_quality.statement}</p><ul>{context.data_quality.warnings.map((warning, index) => <li key={`${warning.source}-${index}`}><strong>{warning.source}</strong><small>{warning.message}</small></li>)}</ul></section> : null}
        </> : null}
        <button type="button" className="qms-audit-preparation-context-refresh" onClick={() => void refresh()} disabled={contextQuery.isFetching}><RefreshCw size={15} /> Refresh preparation context</button>
      </div>
    </aside> : null}
  </>;
};

export default QualityAuditPreparationContextHost;
