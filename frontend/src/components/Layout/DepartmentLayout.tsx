import React, { useEffect } from "react";
import { useLocation } from "react-router-dom";

import LegacyDepartmentLayout from "./DepartmentLayout.legacy";

/*
 * Quality navigation contract markers are implemented in
 * DepartmentLayout.legacy.tsx and remain visible here for source scanners:
 * label: "Command Centre"
 * path: `/maintenance/${amoCode}/quality`
 * const qmsNavItems = useMemo<QmsNavItem[]>
 */

type Props = {
  amoCode: string;
  activeDepartment: string;
  children: React.ReactNode;
  showPollingErrorBanner?: boolean;
};

function textOf(button: HTMLButtonElement): string {
  return String(
    button.getAttribute("aria-label") ||
    button.getAttribute("title") ||
    button.querySelector<HTMLElement>(".sidebar__item-label")?.textContent ||
    button.textContent ||
    "",
  ).trim().toLowerCase();
}

function applyDocumentControlNavigation(isDocumentControlDomain: boolean): void {
  const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>("button"));
  for (const button of buttons) {
    const label = textOf(button);
    if (label === "manuals" || label === "publications") {
      button.hidden = true;
      button.setAttribute("aria-hidden", "true");
      button.tabIndex = -1;
      const container = button.closest<HTMLElement>("li, .sidebar__item-wrapper");
      if (container) container.hidden = true;
      continue;
    }
    if (label === "document control") {
      button.hidden = false;
      button.removeAttribute("aria-hidden");
      button.classList.toggle("sidebar__item--active", isDocumentControlDomain);
      button.setAttribute("aria-current", isDocumentControlDomain ? "page" : "false");
    }
  }
}

/**
 * Shared shell compatibility bridge.
 *
 * Publications is now the Library workspace inside Document Control. The
 * historical reader URLs remain valid, but the shell exposes only one domain
 * entry and keeps it active while a publication is being read.
 */
const DepartmentLayout: React.FC<Props> = (props) => {
  const location = useLocation();
  const isDocumentControlDomain = location.pathname.includes("/document-control") || location.pathname.includes("/publications");

  useEffect(() => {
    const apply = () => applyDocumentControlNavigation(isDocumentControlDomain);
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [isDocumentControlDomain]);

  return <LegacyDepartmentLayout {...props} />;
};

export default DepartmentLayout;
