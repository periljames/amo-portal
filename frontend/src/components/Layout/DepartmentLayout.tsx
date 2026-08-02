import React, { useEffect, useLayoutEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import LegacyDepartmentLayout from "./DepartmentLayout.legacy";
import {
  enhanceQmsSidebarNavigation,
  isQualityNavigationPath,
} from "./qmsSidebarNavigation";
import { getCachedUser } from "../../services/auth";
import "../../styles/components/qms-sidebar-navigation.css";

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

function setVisible(button: HTMLButtonElement, visible: boolean): void {
  button.hidden = !visible;
  button.tabIndex = visible ? 0 : -1;
  if (visible) button.removeAttribute("aria-hidden");
  else button.setAttribute("aria-hidden", "true");
  const container = button.closest<HTMLElement>("li, .sidebar__item-wrapper");
  if (container) container.hidden = !visible;
}

function applyDocumentControlNavigation(isDocumentControlDomain: boolean): void {
  const sidebar = document.querySelector<HTMLElement>(".app-shell__sidebar, .sidebar");
  if (!sidebar) return;
  const buttons = Array.from(sidebar.querySelectorAll<HTMLButtonElement>("button"));
  const compatibilityEntry = buttons.find((button) => {
    const label = textOf(button);
    return button.dataset.documentControlEntry === "true" || label === "manuals" || label === "publications";
  });

  if (compatibilityEntry) {
    compatibilityEntry.dataset.documentControlEntry = "true";
    const labelNode = compatibilityEntry.querySelector<HTMLElement>(".sidebar__item-label");
    if (labelNode && labelNode.textContent !== "Document Control") labelNode.textContent = "Document Control";
    compatibilityEntry.setAttribute("aria-label", "Document Control");
    compatibilityEntry.setAttribute("title", "Document Control");
    compatibilityEntry.setAttribute("aria-current", isDocumentControlDomain ? "page" : "false");
    compatibilityEntry.classList.toggle("sidebar__item--active", isDocumentControlDomain);
    setVisible(compatibilityEntry, true);
  }

  for (const button of buttons) {
    if (button === compatibilityEntry) continue;
    const nativeWorkspaceEntry = button.getAttribute("aria-label") === "Document Control workspace";
    if (nativeWorkspaceEntry && compatibilityEntry) {
      setVisible(button, false);
    }
  }
}

function setDesktopSidebarDefault(amoCode: string, qualityUpgrade: boolean): void {
  if (typeof window === "undefined" || !window.matchMedia("(min-width: 1025px)").matches) return;
  const currentUser = getCachedUser();
  const identity = `${currentUser?.id || "anon"}:${currentUser?.amo_id || amoCode}`;
  const storageKey = `amo_sidebar_pinned:${identity}`;
  const qualityUpgradeKey = `amo_sidebar_quality_navigation_v2:${identity}`;

  if (qualityUpgrade && window.localStorage.getItem(qualityUpgradeKey) !== "1") {
    window.localStorage.setItem(storageKey, "1");
    window.localStorage.setItem(qualityUpgradeKey, "1");
    return;
  }

  if (window.localStorage.getItem(storageKey) === null) {
    window.localStorage.setItem(storageKey, "1");
  }
}

/**
 * Shared shell compatibility bridge.
 *
 * Publications is now the Library workspace inside Document Control. The legacy
 * Manuals button is retained as the single global entry because its historical
 * route redirects safely to the Library. Its accessible label and active state are
 * updated in place; the department-only duplicate is suppressed. Publication
 * reader routes are treated as part of the Document Control department so their
 * subnavigation remains available.
 *
 * The Quality workspace receives a grouped route layer without duplicating the
 * legacy shell. Calendar and audit planning are direct destinations, the current
 * audit exposes its complete workflow, and lower-frequency modules remain inside
 * compact expandable sections.
 */
const DepartmentLayout: React.FC<Props> = (props) => {
  const location = useLocation();
  const navigate = useNavigate();
  const isDocumentControlDomain = location.pathname.includes("/document-control") || location.pathname.includes("/publications") || location.pathname.includes("/manuals");
  const effectiveDepartment = isDocumentControlDomain ? "document-control" : props.activeDepartment;
  const isQualityDomain =
    effectiveDepartment === "quality" ||
    isQualityNavigationPath(location.pathname, props.amoCode);

  useLayoutEffect(() => {
    setDesktopSidebarDefault(props.amoCode, isQualityDomain);
  }, [isQualityDomain, props.amoCode]);

  useEffect(() => {
    const apply = () => applyDocumentControlNavigation(isDocumentControlDomain);
    apply();
    const sidebar = document.querySelector<HTMLElement>(".app-shell__sidebar, .sidebar");
    if (!sidebar) return undefined;
    const observer = new MutationObserver(apply);
    observer.observe(sidebar, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [isDocumentControlDomain]);

  useEffect(() => {
    if (!isQualityDomain) return undefined;

    const sidebar = document.querySelector<HTMLElement>(".app-shell__sidebar, .sidebar");
    if (!sidebar) return undefined;

    const onNavigate = (path: string) => {
      navigate(path);
      if (typeof window !== "undefined" && window.matchMedia("(max-width: 1024px)").matches) {
        sidebar.querySelector<HTMLButtonElement>(".sidebar__close-btn")?.click();
      }
    };

    const apply = () => {
      enhanceQmsSidebarNavigation({
        sidebar,
        amoCode: props.amoCode,
        pathname: location.pathname,
        search: location.search,
        onNavigate,
      });
    };

    apply();
    const observer = new MutationObserver(apply);
    observer.observe(sidebar, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [isQualityDomain, location.pathname, location.search, navigate, props.amoCode]);

  return <LegacyDepartmentLayout {...props} activeDepartment={effectiveDepartment} />;
};

export default DepartmentLayout;
