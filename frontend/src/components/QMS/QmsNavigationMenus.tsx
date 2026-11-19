import React, { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { QMS_ROUTE_REGISTRY, qmsBasePath, qmsModulePath } from "../../pages/qms/routes/qmsRouteRegistry";
import { qmsPeopleWorkspacePath, qmsWorkspaceEntryPath } from "../../pages/qms/routes/qmsWorkspaceRegistry";
import { qmsViewLabel } from "../../pages/qms/qmsWorkspaceCopy";
import { qmsNavigationCatalogue, searchQualityDestinations, qmsViewPermission } from "./qmsNavigationCatalogue";

const groups = [
  { id: "work", label: "Work", sections: ["command"] },
  { id: "assurance", label: "Assurance", sections: ["assurance"] },
  { id: "controls", label: "Controls & settings", sections: ["control", "administration"] },
  { id: "reports", label: "Reports", sections: ["reporting"] },
] as const;

const visibleControl = (element: HTMLElement) => element.getClientRects().length > 0;

function QmsNavigationMenusContent({ amoCode }: { amoCode: string }) {
  const location = useLocation();
  const root = useRef<HTMLElement>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const catalogue = qmsNavigationCatalogue(amoCode).filter(item => hasQmsRolePermission(item.permission));
  const results = searchQualityDestinations(catalogue, search);
  const base = qmsBasePath(amoCode);
  const moduleActive = (segment: string) => location.pathname === `${base}/${segment}` || location.pathname.startsWith(`${base}/${segment}/`);
  const openGroup = (id: string) => {
    setOpen(id);
  };
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(null); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape" && root.current?.querySelector('button[aria-expanded="true"]')) { event.preventDefault(); const active = root.current?.querySelector<HTMLButtonElement>('button[aria-expanded="true"]'); setOpen(null); active?.focus({ preventScroll: true }); } };
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, []);
  const current = (path: string) => `${location.pathname}${location.search}` === path;
  const link = (path: string, label: string) => <Link key={path} to={path} data-preload-route={path} aria-current={current(path) ? "page" : undefined} onClick={() => setOpen(null)}>{label}</Link>;
  const panelKeys = (event: React.KeyboardEvent<HTMLElement>) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const targets = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("a[href], summary")).filter(visibleControl);
    if (!targets.length) return;
    event.preventDefault(); event.stopPropagation();
    const index = targets.indexOf(document.activeElement as HTMLElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? targets.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + targets.length) % targets.length;
    targets[next]?.focus({ preventScroll: true });
    targets[next]?.scrollIntoView({ block: "nearest" });
  };
  return <nav ref={root} className="qms-menu-bar quality-context-bar" aria-label="QMS page menus" onBlur={event => { if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(null); }}>
    <Link className="qms-menu-bar__home" to={base} onClick={() => setOpen(null)}>QMS</Link>
    {groups.map(group => {
      const modules = QMS_ROUTE_REGISTRY.filter(module => (group.sections as readonly string[]).includes(module.section) && !["documents", "aerodoc"].includes(module.id) && hasQmsRolePermission(module.permission));
      const hubDestinations = group.id === "controls" ? catalogue.filter(item => item.moduleLabel === "Assurance controls") : [];
      if (!modules.length && group.id !== "work" && !hubDestinations.length) return null;
      const active = modules.some(module => moduleActive(module.segment)) || hubDestinations.some(item => current(item.path));
      return <div className="qms-page-menu" key={group.id}>
        <button type="button" className={active ? "is-active" : undefined} aria-expanded={open === group.id} aria-controls={`qms-menu-${group.id}`} onClick={() => open === group.id ? setOpen(null) : openGroup(group.id)} onKeyDown={event => {
          if (["ArrowDown", "ArrowUp"].includes(event.key)) {
            event.preventDefault(); openGroup(group.id);
            const last = event.key === "ArrowUp";
            requestAnimationFrame(() => { const targets = Array.from(root.current?.querySelectorAll<HTMLElement>(`#qms-menu-${group.id} a[href], #qms-menu-${group.id} summary`) || []).filter(visibleControl); (last ? targets.at(-1) : targets[0])?.focus({ preventScroll: true }); });
          } else if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
            event.preventDefault();
            const buttons = Array.from(root.current?.querySelectorAll<HTMLButtonElement>(".qms-page-menu > button") || []);
            const next = buttons[(buttons.indexOf(event.currentTarget) + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length];
            next?.focus({ preventScroll: true }); if (open && next?.getAttribute("aria-expanded") !== "true") next?.click();
          }
        }}>{group.label}<ChevronDown size={14} aria-hidden="true" /></button>
        {open === group.id && <nav className="qms-page-menu__panel" id={`qms-menu-${group.id}`} onKeyDown={panelKeys} aria-label={group.id === "controls" ? "QMS controls and settings" : `${group.label} pages`}>
          {group.id === "work" && <>
            {link(base, "Control Room")}
            {hasQmsRolePermission("qms.change.view") && link(qmsWorkspaceEntryPath(amoCode, "missions"), "Missions")}
            {hasQmsRolePermission("qms.people.view") && link(qmsPeopleWorkspacePath(amoCode), "People & authorizations")}
          </>}
          {group.id === "assurance" && hasQmsRolePermission("qms.audit.view") && link(`${base}?workspace=assurance`, "Assurance cases")}
          {group.id === "reports" && hasQmsRolePermission("qms.reports.view") && link(qmsWorkspaceEntryPath(amoCode, "intelligence"), "Quality Intelligence")}
          {modules.map(module => <div className="qms-page-menu__destination" key={module.id}>
            {link(qmsModulePath(amoCode, module.id, module.defaultView), module.navigationLabel)}
            <div className="qms-page-menu__views">{module.validViews.filter(view => view !== module.defaultView && hasQmsRolePermission(qmsViewPermission(module, view))).map(view => link(qmsModulePath(amoCode, module.id, view), `${qmsViewLabel(view)}`))}</div>
          </div>)}
          {hubDestinations.length > 0 && <div className="qms-page-menu__destination">
            {link(hubDestinations[0].path, hubDestinations[0].label)}
            <div className="qms-page-menu__views">{hubDestinations.slice(1).map(item => link(item.path, item.label))}</div>
          </div>}
        </nav>}
      </div>;
    })}
    <div className="qms-page-menu qms-page-menu--directory">
      <button type="button" aria-expanded={open === "directory"} aria-controls="qms-page-directory" onClick={() => { setOpen(open === "directory" ? null : "directory"); setSearch(""); requestAnimationFrame(() => root.current?.querySelector<HTMLInputElement>("#qms-page-search")?.focus()); }}>Find a page<ChevronDown size={14} aria-hidden="true" /></button>
      {open === "directory" && <section className="qms-page-menu__panel qms-page-directory" id="qms-page-directory" aria-label="Quality page directory">
        <label htmlFor="qms-page-search">Find any Quality page</label><input id="qms-page-search" type="search" placeholder="Try minutes, calibration, audit or people" value={search} onChange={event => setSearch(event.target.value)} autoComplete="off" />
        <p role="status">{results.length} accessible destinations</p>
        <nav aria-label="Quality page search results" onKeyDown={panelKeys}>{results.map(item => <Link key={item.path} to={item.path} onClick={() => setOpen(null)} aria-current={current(item.path) ? "page" : undefined}><strong>{item.label}</strong><small>{item.moduleLabel}</small></Link>)}</nav>
        {!results.length && <p>No accessible page matches. Try a module name or a shorter search.</p>}
      </section>}
    </div>
  </nav>;
}

export default function QmsNavigationMenus({ amoCode }: { amoCode: string }) {
  const location = useLocation();
  return <QmsNavigationMenusContent key={location.key} amoCode={amoCode}/>;
}
