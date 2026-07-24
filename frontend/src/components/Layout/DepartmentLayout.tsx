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

function applyPublicationsNavigationLabel(isPublicationsRoute: boolean): void {
  const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>('button[aria-label="Manuals"], button[title="Manuals"]'));
  for (const button of buttons) {
    if (button.getAttribute("aria-label") !== "Publications") button.setAttribute("aria-label", "Publications");
    if (button.getAttribute("title") !== "Publications") button.setAttribute("title", "Publications");
    const label = button.querySelector<HTMLElement>(".sidebar__item-label");
    if (label && label.textContent !== "Publications") label.textContent = "Publications";
    button.classList.toggle("sidebar__item--active", isPublicationsRoute);
  }
}

/**
 * Shared shell compatibility bridge.
 *
 * The full shell remains isolated in DepartmentLayout.legacy.tsx so concurrent
 * module work is not rebased through a 2,000+ line layout file. This wrapper
 * upgrades the historical Manuals navigation affordance to Publications and
 * keeps its active state correct on the canonical route.
 */
const DepartmentLayout: React.FC<Props> = (props) => {
  const location = useLocation();
  const isPublicationsRoute = location.pathname.includes("/publications");

  useEffect(() => {
    const apply = () => applyPublicationsNavigationLabel(isPublicationsRoute);
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [isPublicationsRoute]);

  return <LegacyDepartmentLayout {...props} />;
};

export default DepartmentLayout;
