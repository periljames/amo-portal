import type { ReactNode } from "react";
import { ArrowLeft, Cloud, CloudOff, RefreshCw, Users } from "lucide-react";
import ThemeToggle from "../../../components/UI/ThemeToggle";
import "./auditFieldworkPresentation.css";

type Props = {
  title: string; auditRef: string; backLink: ReactNode; completed: number; total: number;
  pending: number; connectivity: string; teamCount: number; readOnly: boolean;
  actions: ReactNode; syncActions: ReactNode; syncMessage: string; attention?: boolean;
};

export default function AuditFieldworkHeader(props: Props) {
  const percent = props.total ? Math.round(props.completed / props.total * 100) : 0;
  return <>
    <header className="audit-fieldwork-header">
      <div className="audit-fieldwork-header__identity">
        <div className="audit-fieldwork-header__eyebrow"><span className="audit-fieldwork-header__back"><ArrowLeft size={14} aria-hidden />{props.backLink}</span><span aria-hidden>/</span><span>{props.auditRef}</span><span className="audit-fieldwork-header__stage">Fieldwork</span></div>
        <h1>{props.title}</h1>
        <p>Work through the source checklist. Keep your assessment and evidence together.</p>
      </div>
      <div className="audit-fieldwork-header__actions"><ThemeToggle />{props.readOnly ? <span className="audit-fieldwork-header__readonly">Read-only</span> : null}{props.actions}</div>
    </header>
    <section className="audit-fieldwork-status" aria-label="Fieldwork progress and synchronization">
      <div className="audit-fieldwork-status__progress">
        <div><strong>{props.completed}<span> / {props.total}</span></strong><span>server-confirmed</span></div>
        <progress value={props.completed} max={props.total || 1} aria-label="Server-confirmed checklist progress" />
        <span className="audit-fieldwork-status__percent">{props.total ? `${percent}%` : "No questions"}</span>
      </div>
      <div className="audit-fieldwork-status__sync" data-attention={props.attention || undefined} role="status" aria-live="polite">
        <span className="audit-fieldwork-status__connection" data-state={props.connectivity}>
          {props.connectivity === "ONLINE" ? <Cloud size={15} aria-hidden /> : props.connectivity === "RECOVERING" ? <RefreshCw size={15} aria-hidden /> : <CloudOff size={15} aria-hidden />}
          {props.connectivity === "ONLINE" ? "Online" : props.connectivity === "RECOVERING" ? "Reconnecting" : "Offline"}
        </span>
        <span>{props.syncMessage}</span>
        {props.pending ? <span className="audit-fieldwork-status__pending">{props.pending} on device</span> : null}
        {props.syncActions}
      </div>
      <span className="audit-fieldwork-status__team"><Users size={14} aria-hidden />{props.teamCount} active</span>
    </section>
  </>;
}
