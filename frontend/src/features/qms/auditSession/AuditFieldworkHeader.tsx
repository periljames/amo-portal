import type { ReactNode } from "react";
import { ArrowLeft, Cloud, CloudOff, RefreshCw, Users } from "lucide-react";
import ThemeToggle from "../../../components/UI/ThemeToggle";
import "./auditFieldworkPresentation.css";

type Props = {
  title: string; auditRef: string; backLink: ReactNode; completed: number; total: number;
  pending: number; connectivity: string; teamCount: number; readOnly: boolean;
  actions: ReactNode; syncActions: ReactNode; syncMessage: string; attention?: boolean;
  embedded?: boolean;
  teamDetails?: ReactNode;
};

export default function AuditFieldworkHeader(props: Props) {
  const percent = props.total ? Math.round(props.completed / props.total * 100) : 0;
  return <header className="audit-fieldwork-header audit-fieldwork-header--compact">
    <div className="audit-fieldwork-header__identity">
      <div className="audit-fieldwork-header__eyebrow"><span className="audit-fieldwork-header__back"><ArrowLeft size={14} aria-hidden />{props.backLink}</span><span>{props.auditRef}</span></div>
      <h1>{props.title}</h1>
    </div>
    <div className="audit-fieldwork-header__meter" aria-label="Checklist progress">
      <span>{props.completed} / {props.total}</span><progress value={props.completed} max={props.total || 1} aria-label="Checklist progress" /><span>{percent}%</span>
    </div>
    <div className="audit-fieldwork-header__sync" role="status" data-attention={props.attention || undefined} title={props.syncMessage}>
      {props.connectivity === "ONLINE" ? <Cloud size={15} aria-hidden /> : props.connectivity === "RECOVERING" ? <RefreshCw size={15} aria-hidden /> : <CloudOff size={15} aria-hidden />}
      <span>{props.pending ? `${props.pending} awaiting sync` : props.connectivity === "ONLINE" ? "Connected" : "Working offline"}</span>
    </div>
    <div className="audit-fieldwork-header__actions">
      <details className="audit-fieldwork-team"><summary aria-label="Audit team and activity"><Users size={17} aria-hidden /><span>{props.teamCount} active</span></summary>
        <div className="audit-fieldwork-team__panel"><h2>Team & audit activity</h2><p role="status">{props.syncMessage}</p>{props.syncActions}{props.teamDetails}</div>
      </details>
      <ThemeToggle />{props.readOnly ? <span className="audit-fieldwork-header__readonly">Read-only</span> : null}{props.actions}
    </div>
  </header>;
}
