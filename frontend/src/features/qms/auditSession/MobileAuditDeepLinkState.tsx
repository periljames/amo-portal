import React from "react";
import { ClipboardCheck } from "lucide-react";
import { useLocation } from "react-router-dom";

/**
 * Responsive audit run navigation historically collapses differently across
 * route generations. A deep link such as `?tab=closeout` must still project an
 * explicit, operable current-state control after a mobile reload even when the
 * wider desktop tab strip is not rendered.
 *
 * This component does not own lifecycle routing. It mirrors only the current
 * deep-linked state, and delegates scrolling/focus to the mounted closeout
 * workspace. Therefore it cannot create or switch an audit state on its own.
 */
const MobileAuditDeepLinkState: React.FC = () => {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const tab = (params.get("tab") || "").trim().toLowerCase();
  const isAuditRun = /\/(?:qms|quality)\/audits\/[^/]+\/?$/i.test(location.pathname);

  if (!isAuditRun || tab !== "closeout") return null;

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
