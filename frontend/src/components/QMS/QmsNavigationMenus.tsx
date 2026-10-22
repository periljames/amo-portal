import React, { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { QMS_ROUTE_REGISTRY, qmsBasePath, qmsModulePath } from "../../pages/qms/routes/qmsRouteRegistry";
import { qmsPeopleWorkspacePath, qmsWorkspaceEntryPath } from "../../pages/qms/routes/qmsWorkspaceRegistry";
import { qmsViewLabel } from "../../pages/qms/qmsWorkspaceCopy";

const groups = [
  { id: "work", label: "Work", sections: ["command"] },
  { id: "assurance", label: "Assurance", sections: ["assurance"] },
  { id: "controls", label: "Controls & settings", sections: ["control", "administration"] },
  { id: "reports", label: "Reports", sections: ["reporting"] },
] as const;

export default function QmsNavigationMenus({ amoCode }: { amoCode: string }) {
  const location = useLocation();
  const root = useRef<HTMLElement>(null);
  const [open, setOpen] = useState<string | null>(null);
  const base = qmsBasePath(amoCode);
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(null); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { const active = root.current?.querySelector<HTMLButtonElement>('button[aria-expanded="true"]'); setOpen(null); active?.focus(); } };
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, []);
  const current = (path: string) => `${location.pathname}${location.search}` === path;
  const link = (path: string, label: string) => <Link key={path} to={path} aria-current={current(path) ? "page" : undefined} onClick={() => setOpen(null)}>{label}</Link>;
  return <nav ref={root} className="qms-menu-bar quality-context-bar" aria-label="QMS page menus">
    <Link className="qms-menu-bar__home" to={base} onClick={() => setOpen(null)}>QMS</Link>
    {groups.map(group => {
      const modules = QMS_ROUTE_REGISTRY.filter(module => (group.sections as readonly string[]).includes(module.section) && module.id !== "aerodoc" && hasQmsRolePermission(module.permission));
      if (!modules.length && group.id !== "work") return null;
      const active = modules.some(module => location.pathname.startsWith(`${base}/${module.segment}`));
      return <div className="qms-page-menu" key={group.id}>
        <button type="button" className={active ? "is-active" : undefined} aria-expanded={open === group.id} aria-controls={`qms-menu-${group.id}`} onClick={() => setOpen(open === group.id ? null : group.id)}>{group.label}<ChevronDown size={14} aria-hidden="true" /></button>
        {open === group.id && <nav className="qms-page-menu__panel" id={`qms-menu-${group.id}`} aria-label={group.id === "controls" ? "QMS controls and settings" : `${group.label} pages`}>
          {group.id === "work" && <>
            {link(base, "Control Room")}
            {hasQmsRolePermission("qms.change.view") && link(qmsWorkspaceEntryPath(amoCode, "missions"), "Missions")}
            {hasQmsRolePermission("qms.people.view") && <details className="qms-page-menu__module"><summary>People & authorizations</summary><div>{(["overview", "people", "cases", "reviews", "administration"] as const).map(tab => link(qmsPeopleWorkspacePath(amoCode, { tab }), qmsViewLabel(tab)))}</div></details>}
          </>}
          {modules.map(module => <div className="qms-page-menu__destination" key={module.id}>
            {link(qmsModulePath(amoCode, module.id, module.defaultView), module.id === "settings" ? "Settings" : module.navigationLabel)}
            {module.validViews.length > 1 && <details className="qms-page-menu__module"><summary>{module.navigationLabel} pages</summary><div>{module.validViews.map(view => link(qmsModulePath(amoCode, module.id, view), qmsViewLabel(view)))}</div></details>}
          </div>)}
        </nav>}
      </div>;
    })}
  </nav>;
}
