import { Link, useLocation } from "react-router-dom";
import { useEffect, useRef } from "react";
import { classifyQmsPath, qmsModulePath } from "../../pages/qms/routes/qmsRouteRegistry";
import { qmsViewLabel } from "../../pages/qms/qmsWorkspaceCopy";
import "./qms-section-tabs.css";

export default function QmsSectionTabs({ amoCode }: { amoCode: string }) {
  const { pathname, search } = useLocation();
  const tabs = useRef<HTMLElement>(null);
  useEffect(() => {
    const element = tabs.current;
    if (!element) return;
    const revealActive = () => {
      const active = element.querySelector<HTMLElement>('[aria-current="page"]');
      if (!active) return;
      const bounds = active.getBoundingClientRect();
      const container = element.getBoundingClientRect();
      if (bounds.left < container.left || bounds.right > container.right) {
        element.scrollLeft += bounds.left - container.left - (element.clientWidth - bounds.width) / 2;
      }
    };
    const observer = new ResizeObserver(revealActive);
    observer.observe(element);
    revealActive();
    return () => observer.disconnect();
  }, [pathname]);
  const { module, relativePath } = classifyQmsPath(pathname);
  if (!module || module.validViews.length < 2) return null;
  const view = relativePath?.split("/")[1] || module.defaultView;
  if (!module.validViews.includes(view)) return null;
  const reportLabels: Record<string, string> = { "executive-dashboard": "Executive summary", "car-performance": "CAR performance", "training-compliance": "Training validity" };
  const period = new URLSearchParams(search).get("period");
  const findingsQuery = module.id === "findings" && period ? `?${new URLSearchParams({ period })}` : "";
  return <nav ref={tabs} className="qms-section-tabs" aria-label={`${module.navigationLabel} views`}>
    {module.validViews.filter(item => item !== "new").map(item => <Link key={item} to={`${qmsModulePath(amoCode, module.id, item)}${findingsQuery}`} aria-current={view === item ? "page" : undefined}>{module.id === "reports" ? reportLabels[item] || qmsViewLabel(item) : qmsViewLabel(item)}</Link>)}
  </nav>;
}
