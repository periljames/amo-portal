import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { ArrowLeft, ArrowRight, BookOpen, CalendarDays, Factory, FileText, Gauge, GraduationCap, Grid2X2, Pause, Plane, Play, Settings, ShieldCheck, Warehouse, Wrench, X, type LucideIcon } from "lucide-react";
import { currentPortalApp, type PortalApp } from "../../app/portalApps";
import "./portal-app-selector.css";

const icons: Record<string,LucideIcon>={planning:CalendarDays,production:Factory,maintenance:Wrench,quality:ShieldCheck,documents:FileText,records:BookOpen,rostering:CalendarDays,training:GraduationCap,reliability:Gauge,stores:Warehouse,safety:ShieldCheck,workshops:Wrench,settings:Settings};
function revealTile(tile:HTMLElement){const rail=tile.parentElement;if(!rail)return;const left=tile.offsetLeft-rail.offsetLeft;if(left<rail.scrollLeft)rail.scrollLeft=left;else if(left+tile.offsetWidth>rail.scrollLeft+rail.clientWidth)rail.scrollLeft=left+tile.offsetWidth-rail.clientWidth;}
type Props={apps:PortalApp[];pathname:string;tenantName:string;onClose:()=>void;onSelect:(path:string)=>void};
export default function PortalAppSelector({apps,pathname,tenantName,onClose,onSelect}:Props) {
  const current=currentPortalApp(apps,pathname);
  const [selected,setSelected]=useState(current?.id||apps[0]?.id);
  const [paused,setPaused]=useState(false);
  const [hidden,setHidden]=useState(document.hidden);
  const dialog=useRef<HTMLDivElement>(null);
  const active=apps.find(a=>a.id===selected)||apps[0];
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null;
    const overflow=document.body.style.overflow;
    document.body.style.overflow="hidden";
    const selectedTile=dialog.current?.querySelector<HTMLElement>('[aria-pressed="true"]')||dialog.current?.querySelector<HTMLElement>('button');
    selectedTile?.focus({preventScroll:true});
    if(selectedTile)revealTile(selectedTile);
    const visibility=()=>setHidden(document.hidden);
    document.addEventListener("visibilitychange",visibility);
    return ()=>{document.body.style.overflow=overflow;document.removeEventListener("visibilitychange",visibility);previous?.focus({preventScroll:true});};
  },[]);
  const keys=(event:KeyboardEvent<HTMLDivElement>)=>{
    if(event.key==="Escape"){event.preventDefault();event.stopPropagation();onClose();}
    if(event.key==="Tab"){
      const controls=Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href]')||[]);
      const first=controls[0],last=controls.at(-1);
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    }
  };
  const tileKeys=(event:KeyboardEvent<HTMLButtonElement>,index:number)=>{
    if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;
    event.preventDefault();
    const next=event.key==="Home"?0:event.key==="End"?apps.length-1:(index+(event.key==="ArrowRight"?1:-1)+apps.length)%apps.length;
    dialog.current?.querySelectorAll<HTMLButtonElement>('.portal-apps__tile')[next]?.focus({preventScroll:true});
  };
  return createPortal(<div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="portal-apps-title" className="portal-apps" data-paused={paused||hidden} onKeyDown={keys}>
    <div className="portal-apps__sky" aria-hidden="true">
      <div className="portal-apps__cloud portal-apps__cloud--one"/><div className="portal-apps__cloud portal-apps__cloud--two"/>
      <svg className="portal-apps__airspace" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice"><defs><linearGradient id="airspace-line"><stop stopColor="#80e7ff" stopOpacity="0"/><stop offset=".65" stopColor="#80e7ff" stopOpacity=".6"/><stop offset="1" stopColor="#80e7ff" stopOpacity="0"/></linearGradient></defs><path className="portal-apps__route" d="M-80 790 Q490 60 1570 370"/><path className="portal-apps__route portal-apps__route--second" d="M-60 820 Q620 290 1540 460"/><g className="portal-apps__aircraft"><path d="m0-32 5 22 31 18v6L5 4v20l9 8v4L0 31l-14 5v-4l9-8V4l-31 10V8L-5-10Z" fill="#d6f6ff"/><path d="M0 36v125" stroke="url(#airspace-line)" strokeWidth="2"/></g><g className="portal-apps__horizon" fill="none" stroke="#8cd6ef" strokeOpacity=".15"><ellipse cx="1000" cy="950" rx="830" ry="385"/><ellipse cx="1000" cy="950" rx="650" ry="300"/><path d="m1000 560-600 500m600-500 600 500M-100 780h1600M-100 870h1600"/></g></svg>
    </div>
    <header className="portal-apps__header"><div><span className="portal-apps__brand"><Plane size={20}/> AMO PORTAL</span><span className="portal-apps__tenant">{tenantName}</span></div><button type="button" className="portal-apps__close" onClick={onClose} aria-label="Close app selector"><X size={20}/><span>Back to work</span></button></header>
    <main className="portal-apps__main">
      <div className="portal-apps__eyebrow"><Grid2X2 size={16}/> YOUR WORKSPACES</div>
      <h1 id="portal-apps-title">Choose your next destination.</h1>
      <div className="portal-apps__rail" aria-label="Available apps">{apps.map((app,index)=>{
        const Icon=icons[app.icon]||Grid2X2;
        return <button key={app.id} type="button" className="portal-apps__tile" data-app={app.id} aria-pressed={active?.id===app.id} aria-label={app.name} onFocus={e=>{setSelected(app.id);revealTile(e.currentTarget);}} onClick={()=>setSelected(app.id)} onKeyDown={e=>tileKeys(e,index)}><span className="portal-apps__tile-art"><Icon size={34} strokeWidth={1.4}/><span className="portal-apps__tile-code">{String(index+1).padStart(2,"0")}</span></span><span className="portal-apps__tile-name">{app.name}</span>{current?.id===app.id?<span className="portal-apps__current">Current app</span>:null}</button>;
      })}</div>
      {active?<section className="portal-apps__detail" key={active.id} aria-live="polite"><span className="portal-apps__eyebrow">{current?.id===active.id?"CURRENT WORKSPACE":"READY WHEN YOU ARE"}</span><h2>{active.name}</h2><p>{active.description}</p><button type="button" className="portal-apps__launch" onClick={()=>current?.id===active.id?onClose():onSelect(active.path)}>{current?.id===active.id?"Resume work":"Open app"}<ArrowRight size={18}/></button></section>:<p>No additional apps are assigned to this account.</p>}
    </main>
    <footer className="portal-apps__footer"><span><ArrowLeft size={14}/><ArrowRight size={14}/> Browse apps <span className="portal-apps__keyboard">· Enter to select · Esc to return</span></span><button type="button" onClick={()=>setPaused(!paused)} aria-pressed={paused} aria-label={paused?"Play aviation background":"Pause aviation background"}>{paused?<Play size={14}/>:<Pause size={14}/>}<span>{paused?"Play background":"Pause background"}</span></button></footer>
  </div>,document.body);
}
