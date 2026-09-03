import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";

type Props = { containerId: string; children: React.ReactNode };

/** Portals into a route-owned mount. Retries until the host node exists. */
const OccurrenceToolbarPortal: React.FC<Props> = ({ containerId, children }) => {
  const [node, setNode] = useState<HTMLElement | null>(() =>
    typeof document !== "undefined" ? document.getElementById(containerId) : null,
  );

  useEffect(() => {
    const existing = document.getElementById(containerId);
    if (existing) {
      setNode(existing);
      return;
    }

    let cancelled = false;
    const observer = new MutationObserver(() => {
      const found = document.getElementById(containerId);
      if (!found || cancelled) return;
      setNode(found);
      observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    const poll = window.setInterval(() => {
      const found = document.getElementById(containerId);
      if (!found || cancelled) return;
      setNode(found);
      window.clearInterval(poll);
      observer.disconnect();
    }, 50);

    return () => {
      cancelled = true;
      window.clearInterval(poll);
      observer.disconnect();
    };
  }, [containerId]);

  if (!node) return null;
  return createPortal(children, node);
};

export default OccurrenceToolbarPortal;

export const AUDIT_PREPARE_TOOLBAR_ID = "qms-audit-prepare-toolbar";
export const AUDIT_OCCURRENCE_MOUNT_ID = "qms-audit-occurrence-mount";
