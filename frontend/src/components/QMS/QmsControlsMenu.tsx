import { useEffect, useRef } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, SlidersHorizontal } from "lucide-react";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { QMS_ROUTE_REGISTRY, qmsModulePath } from "../../pages/qms/routes/qmsRouteRegistry";

export default function QmsControlsMenu({ amoCode }: { amoCode: string }) {
  const details = useRef<HTMLDetailsElement>(null);
  const location = useLocation();
  useEffect(() => { if (details.current) details.current.open = false; }, [location.pathname]);
  useEffect(() => {
    const close = (event: Event) => { if (details.current && (event instanceof KeyboardEvent ? event.key === "Escape" : !details.current.contains(event.target as Node))) details.current.open = false; };
    document.addEventListener("pointerdown", close); document.addEventListener("keydown", close);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", close); };
  }, []);
  const controls = QMS_ROUTE_REGISTRY.filter(module => (module.section === "control" || module.section === "administration") && module.id !== "aerodoc" && hasQmsRolePermission(module.permission));
  if (!controls.length) return null;
  return <details className="qms-controls-menu" ref={details}>
    <summary><SlidersHorizontal size={16} /> Controls & settings <ChevronDown size={14} /></summary>
    <nav aria-label="QMS controls and settings" onClick={() => { if (details.current) details.current.open = false; }}>
      <strong>Manage Quality</strong>
      {controls.map(module => <Link key={module.id} to={qmsModulePath(amoCode, module.id)} aria-current={location.pathname.includes(`/quality/${module.segment}`) ? "page" : undefined}>{module.navigationLabel === "Mail Identity" ? "Email notifications" : module.navigationLabel}</Link>)}
    </nav>
  </details>;
}
