import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import QmsNavigationMenus from "./QmsNavigationMenus";

function parseQualityRoute(pathname: string): { amoCode: string; segments: string[] } | null {
  const match = pathname.match(/^\/maintenance\/([^/]+)\/quality(?:\/(.*))?$/i);
  return match ? { amoCode: decodeURIComponent(match[1]), segments: (match[2] || "").split("/").filter(Boolean) } : null;
}

const QualityContextTabs: React.FC = () => {
  const location = useLocation();
  const route = useMemo(() => parseQualityRoute(location.pathname), [location.pathname]);
  const qualityActive = Boolean(route);
  const [mountTarget, setMountTarget] = useState<HTMLElement | null>(null);
  useEffect(() => {
    if (!mountTarget) return;
    const main = mountTarget.closest<HTMLElement>(".tenant-shell__main");
    const measure = () => main?.style.setProperty("--qms-context-height", `${mountTarget.getBoundingClientRect().height}px`);
    const observer = new ResizeObserver(measure);
    observer.observe(mountTarget); measure();
    return () => { observer.disconnect(); main?.style.removeProperty("--qms-context-height"); };
  }, [mountTarget]);

  useEffect(() => {
    if (!qualityActive) {
      document.querySelector(".quality-context-bar-host")?.remove();
      return;
    }

    let activeHost: HTMLDivElement | null = null;
    const syncMount = () => {
      const main = document.querySelector<HTMLElement>(".tenant-shell__main");
      if (!main) {
        if (activeHost && !activeHost.isConnected) activeHost = null;
        setMountTarget(null);
        return;
      }
      let host = main.querySelector<HTMLDivElement>(":scope > .quality-context-bar-host");
      if (!host) {
        host = document.createElement("div");
        host.className = "quality-context-bar-host";
        main.prepend(host);
      }
      activeHost = host;
      setMountTarget((current) => (current === host ? current : host));
    };

    // The tenant shell currently exposes only .tenant-shell__main; no stable portal slot exists.
    syncMount();
    const observer = new MutationObserver(syncMount);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      activeHost?.remove();
    };
  }, [qualityActive]);


  useEffect(() => {
    document.documentElement.classList.toggle("quality-context-active", qualityActive);
    document.documentElement.classList.toggle("quality-context-overview", Boolean(route && route.segments.length === 0));
    return () => document.documentElement.classList.remove("quality-context-active", "quality-context-overview");
  }, [qualityActive, route]);
  return route && mountTarget ? createPortal(<QmsNavigationMenus key={`${location.pathname}${location.search}`} amoCode={route.amoCode} />, mountTarget) : null;
};
export default QualityContextTabs;
