import React,{lazy,Suspense,useEffect,useState} from "react";
import {Link,NavLink,useLocation,useNavigate,useParams} from "react-router-dom";
import {getExternalSession,partnerRequest,PartnerRequestError,type PartnerSession} from "./partnerApi";
import {ActionNotice} from "./PartnerPrimitives";
import "./partner.css";

const Home=lazy(()=>import("./PartnerHome"));
const Organization=lazy(()=>import("./PartnerOrganization"));
const Compliance=lazy(()=>import("./PartnerCompliance"));
const Commerce=lazy(()=>import("./PartnerCommerce"));
const Quality=lazy(()=>import("./PartnerQuality"));
const Activity=lazy(()=>import("./PartnerActivity"));

export type PartnerProps={tenant:string;csrf:string;capabilities:string[];reloadSummary:()=>void};
const sections=[
  {id:"home",name:"Action center",cap:"profile.read"},
  {id:"organization",name:"My organization",cap:"profile.read"},
  {id:"compliance",name:"Compliance",cap:"profile.read"},
  {id:"contracts",name:"Contracts",cap:"contract.read"},
  {id:"quality",name:"Quality",cap:"task.read"},
  {id:"procurement",name:"Procurement",cap:"task.read"},
  {id:"work",name:"Contracted work",cap:"task.read"},
  {id:"activity",name:"Notifications & activity",cap:"profile.read"},
] as const;
export default function ExternalPartnerPage(){
  const {tenant=""}=useParams();
  const location=useLocation();
  const navigate=useNavigate();
  const section=location.pathname.split("/")[3]||"home";
  const [session,setSession]=useState<PartnerSession|null>(null);
  const [csrf,setCsrf]=useState("");
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  const [revision,setRevision]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();setError("");setLoading(true);
    void Promise.all([
      getExternalSession(controller.signal),
      partnerRequest<PartnerSession>(tenant,"session",{signal:controller.signal}),
    ]).then(([proof,account])=>{
      if(controller.signal.aborted)return;
      setSession(account);setCsrf(proof.csrf);
    }).catch((reason)=>{
      if(controller.signal.aborted)return;
      setSession(null);
      if(reason instanceof PartnerRequestError&&[401,403].includes(reason.status)) {
        navigate(reason.status===403?"/vendor/denied":"/vendor/revoked",{replace:true});
      }else setError(reason instanceof Error?reason.message:"Could not open external portal");
    }).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[tenant,navigate,revision]);
  if(loading)return <main className="partner-shell partner-loading" role="status">Checking authorized partner session…</main>;
  if(error)return <main className="partner-shell"><ActionNotice value={error} error/><button onClick={()=>setRevision(v=>v+1)}>Retry access</button><Link to="/vendor/login">Secure vendor login</Link></main>;
  if(!session)return <main className="partner-shell"><Link to="/vendor/login">Sign in to your partner account</Link></main>;
  const capabilities=new Set(session.capabilities);
  const authorized=sections.filter(s=>capabilities.has(s.cap));
  const current=authorized.find(s=>s.id===section);
  const props:PartnerProps={tenant,csrf,capabilities:session.capabilities,reloadSummary:()=>setRevision(v=>v+1)};
  return <div className="partner-shell">
    <header className="partner-topbar">
      <div><span className="partner-brand">AMO PORTAL <strong>PARTNER</strong></span>
        <span className="partner-organization">{session.organization?.legal_name||"External organization"}</span>
      </div>
      <div className="partner-topbar-actions">
        <span className="partner-tenant">{tenant.toUpperCase()}</span>
        <Link to="/vendor/account">Account security</Link>
        <Link to="/vendor/login">Change account</Link>
      </div>
    </header>
    <div className="partner-layout">
      <aside className="partner-sidebar">
        <div className="partner-sidebar__intro"><small>AUTHORIZED WORKSPACE</small>
          <strong>{session.organization?.trading_name||session.organization?.legal_name}</strong>
          <span>{session.role.replaceAll("_"," ")}</span>
        </div>
        <nav aria-label="Partner portal navigation">
          {authorized.map(s=><NavLink key={s.id} to={`/partner/${encodeURIComponent(tenant)}/${s.id}`}
            className={({isActive})=>isActive||(section==="home"&&s.id==="home"&&location.pathname.endsWith(tenant))?"is-active":""}>
            {s.name}</NavLink>)}
        </nav>
        <div className="partner-sidebar__foot">Access is limited to assigned providers, approved scopes and current membership grants.</div>
      </aside>
      <main className="partner-main">
        <header className="partner-page-title">
          <div><small>EXTERNAL PARTNER PORTAL / {tenant.toUpperCase()}</small>
            <h1>{current?.name||"Access not granted"}</h1>
            <p>Authoritative supplier records and Quality controls remain managed by your AMO.</p>
          </div>
          {session.restricted&&<span className="partner-restricted" role="status">Provider access restricted</span>}
        </header>
        {!current?<section className="partner-panel" role="alert">
          This area is not included in your current external grant. Contact your AMO Quality Department to request a review.
        </section>:<Suspense fallback={<div className="partner-state" role="status">Opening workspace…</div>}>
          {section==="home"&&<Home {...props}/>}
          {section==="organization"&&<Organization {...props}/>}
          {section==="compliance"&&<Compliance {...props}/>}
          {(section==="contracts"||section==="procurement"||section==="work")&&<Commerce {...props} section={section}/>}
          {section==="quality"&&<Quality {...props}/>}
          {section==="activity"&&<Activity {...props}/>}
        </Suspense>}
      </main>
    </div>
  </div>;
}
