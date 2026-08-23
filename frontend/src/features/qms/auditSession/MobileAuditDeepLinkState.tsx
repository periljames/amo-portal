import React from "react";
import { ClipboardCheck } from "lucide-react";
import { useLocation } from "react-router-dom";

/** Focus the mounted canonical Closing workspace on small screens. */
const MobileAuditDeepLinkState: React.FC = () => {
  const location = useLocation();
  if (!/\/quality\/audits\/[^/]+\/closing\/?$/i.test(location.pathname)) return null;

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
