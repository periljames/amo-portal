import type { ReactNode } from "react";
import type { Page } from "./partnerApi";

export function Section({title,description,children,action}:{
  title:string;description?:string;children:ReactNode;action?:ReactNode;
}){
  return <section className="partner-panel">
    <header className="partner-panel__head"><div><h2>{title}</h2>{description&&<p>{description}</p>}</div>{action}</header>
    {children}
  </section>;
}
export function State({pending,error,retry,empty=false}:{
  pending:boolean;error:string;retry:()=>void;empty?:boolean;
}) {
  if(pending)return <div className="partner-state" role="status">Loading authorized records…</div>;
  if(error)return <div className="partner-state partner-state--error" role="alert">
    {error} <button type="button" onClick={retry}>Retry</button>
  </div>;
  if(empty)return <div className="partner-state">No records are currently available for this organization and access grant.</div>;
  return null;
}
export function Pager({value,onChange}:{
  value:Page<unknown>;onChange:(offset:number)=>void;
}){
  return <nav className="partner-pager" aria-label="Results pages">
    <span>Showing {value.items.length?value.offset+1:0}–{value.offset+value.items.length}</span>
    <button disabled={value.offset===0} onClick={()=>onChange(Math.max(0,value.offset-value.limit))}>Previous</button>
    <button disabled={!value.has_more} onClick={()=>onChange(value.next_offset??value.offset+value.limit)}>Next</button>
  </nav>;
}
export function Status({value}:{value:string|null|undefined}){
  const text=String(value||"UNRECORDED").replaceAll("_"," ");
  return <span className="partner-status" data-state={value||"UNRECORDED"}>{text}</span>;
}
export function ActionNotice({value,error}: {value:string;error?:boolean}){
  return value?<div className={error?"partner-message is-error":"partner-message"} role={error?"alert":"status"}>{value}</div>:null;
}
