import { buildPortalNavigation, type PortalNavigationContext, type PortalNavIcon } from "./portalRouteManifest";
import { isTenantAdmin } from "../utils/tenantAccess";

export type PortalApp = { id: string; name: string; path: string; scopePath?: string; icon: PortalNavIcon; description: string };
const descriptions: Record<string,string> = {
  quality:"Assurance, findings and controlled approvals.", planning:"Plan maintenance. Keep the fleet ready.",
  production:"Coordinate work, people and aircraft release.", maintenance:"Carry out and record maintenance work.",
  "document-control":"Current publications and controlled records.", reliability:"Fleet performance and continuing airworthiness.",
  safety:"Report, assess and manage operational risk.", procurement:"Providers, sourcing and purchase orders.",
  stores:"Parts, inventory and material traceability.", workshops:"Component work and workshop operations.",
  "technical-records":"Aircraft histories and maintenance records.", "duty-rostering":"Duty plans and team availability.",
  "training-competence":"Training, competence and authorizations.", administration:"Tenant configuration and access management.",
};

/** Use the same permission-filtered destinations as navigation, even inside QMS. */
export function getPortalApps(context: PortalNavigationContext): PortalApp[] {
  const groups=buildPortalNavigation({...context,activeDepartment:undefined});
  const apps: PortalApp[]=[];
  for(const group of groups.filter(g=>["departments","shared-workspaces"].includes(g.id))) {
    for(const item of group.items) {
      const id=item.id.replace(/^department-/,"");
      const grants=context.user?.module_access;
      const moduleKeys:Record<string,string[]>={"document-control":["documents"],production:["production","technical_records"],"technical-records":["technical_records"],"duty-rostering":["rostering"],"training-competence":["training"]};
      if(grants!==undefined&&!isTenantAdmin(context.user)&&!(moduleKeys[id]||[id]).some(key=>Boolean(grants[key])))continue;
      if(item.children?.length===0) continue;
      apps.push({id,name:id==="quality"?"QMS":item.label,path:item.path,scopePath:id==="training-competence"?item.path.replace(/\/competence\/control-room$/,""):item.path,icon:item.icon||"home",description:descriptions[id]||"Your operational workspace."});
    }
  }
  if(groups.some(g=>g.id==="admin-organisation")) {
    apps.push({id:"administration",name:"Administration",path:`/maintenance/${encodeURIComponent(context.amoCode)}/admin/overview`,scopePath:`/maintenance/${encodeURIComponent(context.amoCode)}/admin`,icon:"settings",description:descriptions.administration});
  }
  // Personal training is available even when the user cannot manage competence.
  const personal=groups.find(g=>g.id==="workspace")?.items;
  if(!apps.some(a=>a.id==="training-competence")) {
    const training=personal?.find(i=>i.id==="my-training");
    if(training) apps.push({id:"my-training",name:"My Training",path:training.path,icon:"training",description:"Your courses, attendance and training records."});
  }
  if(!apps.some(a=>a.id==="duty-rostering")) {
    const roster=personal?.find(i=>i.id==="my-roster");
    if(roster) apps.push({id:"my-roster",name:"My Roster",path:roster.path,icon:"rostering",description:"Your duty roster and upcoming assignments."});
  }
  return apps;
}

export function currentPortalApp(apps: PortalApp[], pathname: string): PortalApp | undefined {
  return [...apps].sort((a,b)=>(b.scopePath||b.path).length-(a.scopePath||a.path).length).find(app=>{const scope=app.scopePath||app.path;return pathname===scope||pathname.startsWith(`${scope}/`);});
}
