import React from "react";
import { ClipboardCheck } from "lucide-react";
import { useLocation } from "react-router-dom";

/**
 * Preserve an explicit mobile control for both the canonical Closing stage and
 * legacy closeout deep links. The component never owns lifecycle state; it only
 * focuses the already mounted canonical closing workspace.
 */
const MobileAuditDeepLinkState: React.FC = () => {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const tab = (params.get("tab") || "").trim().toLowerCase();
  const canonicalClosing = /\/(?:qms|quality)\/audits\/[^/]+\/closing\/?$/i.test(location.pathname);
  const legacyAuditRun = /\/(?:qms|quality)\/audits\/[^/]+\/?$/i.test(location.pathname);
  const shouldRender = canonicalClosing || (legacyAuditRun && ["closeout", "report"].includes(tab));

  if (!shouldRender) return null;

  const focusCloseout = () => {
    const target = document.querySelector<HTMLElement>(
      '[data-qms-audit-closeout], [aria-label="Audit closing meeting workspace"], [aria-label*="closeout" i]',
    );
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
      target.focus({ preventScroll: true });
      return;
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="qms-mobile-audit-deep-link" role="navigation" aria-label="Current audit workspace">
      <button type="button" aria-current="page" onClick={focusCloseout}>
        <ClipboardCheck size={16} />
        <span>Report &amp; closeout</span>
      </button>
    </div>
  );
};

export default MobileAuditDeepLinkState;
