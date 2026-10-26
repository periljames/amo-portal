import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import "./auditFieldworkPresentation.css";

export default function AuditWorkspaceDetails({ children, pendingChecks = 0 }: { children: ReactNode; pendingChecks?: number }) {
  return <details className="audit-fieldwork-utilities">
    <summary><ChevronDown size={14} aria-hidden />Audit details &amp; source
      {pendingChecks ? <span className="audit-fieldwork-utilities__checks">{pendingChecks} completion checks</span> : null}
    </summary>
    <div className="audit-fieldwork-utilities__content">{children}</div>
  </details>;
}
