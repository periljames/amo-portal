import React from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, RefreshCw } from "lucide-react";

type Props = {
  className: string;
  title: string;
  detail?: string | null;
  onRetry?: () => void;
  exitHref: string;
  exitLabel?: string;
  secondaryHref?: string;
  secondaryLabel?: string;
};

/** Full-stage failure UI: human copy + retry/exit — never a bare API status string. */
export function AuditStageLoadError({
  className,
  title,
  detail,
  onRetry,
  exitHref,
  exitLabel = "Exit",
  secondaryHref,
  secondaryLabel,
}: Props) {
  const raw = (detail || "").trim();
  const looksLikeHttp =
    /^not found$/i.test(raw) ||
    /^unauthorized$/i.test(raw) ||
    /^forbidden$/i.test(raw) ||
    /^internal server error$/i.test(raw) ||
    /^\d{3}\b/.test(raw) ||
    /\b(?:API|HTTP|QMS API)\s*\d{3}\b/i.test(raw);

  const explanation = !raw
    ? "This stage could not be loaded."
    : looksLikeHttp
      ? "The server could not provide this audit stage right now. Retry, or return to Setup and continue from the next available action."
      : raw;

  return (
    <div className={className} role="alert">
      <AlertTriangle size={22} aria-hidden />
      <div className="qms-audit-stage-load-error__copy">
        <strong>{title}</strong>
        <p>{explanation}</p>
      </div>
      <div className="qms-audit-stage-load-error__actions">
        {onRetry ? (
          <button type="button" className="is-primary" onClick={onRetry}>
            <RefreshCw size={15} /> Retry
          </button>
        ) : null}
        <Link to={exitHref}>{exitLabel}</Link>
        {secondaryHref && secondaryLabel ? <Link to={secondaryHref}>{secondaryLabel}</Link> : null}
      </div>
    </div>
  );
}

export default AuditStageLoadError;
