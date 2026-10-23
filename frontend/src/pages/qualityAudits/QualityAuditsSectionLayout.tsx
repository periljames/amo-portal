import React from "react";
import { useLocation, useParams } from "react-router-dom";
import AuditPageShell from "../../components/QMS/AuditPageShell";
import { getContext } from "../../services/auth";
import "./quality-audits-workspace.css";
import "./qa-dark-contrast.css";
import "../../styles/qms/assurance-workspace.css";

type Props = { title: string; subtitle: string; children: React.ReactNode; toolbar?: React.ReactNode; recordDetail?: boolean };
export default function QualityAuditsSectionLayout({ title, subtitle, children, toolbar, recordDetail = false }: Props) {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const context = getContext();
  const location = useLocation();
  const amoCode = params.amoCode ?? context.amoCode ?? "UNKNOWN";
  const calendar = location.pathname.includes("/quality/calendar");
  const records = /\/quality\/(?:audits\/(?:register|workspace|bin)(?:\/|$)|evidence-vault(?:\/|$))/.test(location.pathname);
  return <AuditPageShell amoCode={amoCode} department={params.department ?? "quality"} title={title} subtitle={subtitle} breadcrumbs={[]} suppressHeader>
    <div className={`qms-surface-root qa-workspace-shell qa-workspace-shell--unified${calendar ? " qa-workspace-shell--calendar-focus" : ""}${records ? " qa-workspace-shell--records" : ""}${recordDetail ? " qa-workspace-shell--record-detail" : ""}`}>
      <section className="qa-workspace-main" aria-label="Current Assurance workspace">
        {!calendar && !recordDetail && <header className="qa-workspace-current-page-heading qa-workspace-page-title"><h1>{title}</h1>{toolbar}</header>}
        {children}
      </section>
    </div>
  </AuditPageShell>;
}
