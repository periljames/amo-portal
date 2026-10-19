import React,{useState} from "react";
import type {PartnerProps} from "./ExternalPartnerPage";
import {friendlyDate,label,partnerRequest,type Change,type Organization,type Page} from "./partnerApi";
import {ActionNotice,Pager,Section,State,Status} from "./PartnerPrimitives";
import { usePartnerLoad } from "./usePartnerLoad";

type Kind="sites"|"contacts"|"capabilities";
type Category="IDENTITY"|"CONTACT"|"SITE"|"CAPABILITY"|"BANKING"|"RENEWAL";
const fields:Record<Category,Array<{id:string;name:string}>>={
  IDENTITY:[{id:"legal_name",name:"Legal name (review required)"},{id:"trading_name",name:"Trading name"},{id:"email",name:"Business email"},{id:"phone",name:"Phone"},
    {id:"physical_address",name:"Business address"},{id:"website",name:"Website"},{id:"country",name:"Country"}],
  CONTACT:[{id:"contact_name",name:"Contact name"},{id:"email",name:"Contact email"},{id:"phone",name:"Contact phone"},{id:"assignment",name:"Assigned function"}],
  SITE:[{id:"site_code",name:"Site code"},{id:"site_name",name:"Site name"},{id:"address",name:"Site address"},{id:"country",name:"Site country"}],
  CAPABILITY:[{id:"description",name:"Capability description"},{id:"rating",name:"Approved rating proposal"},{id:"limitations",name:"Limitations"},{id:"aircraft_type",name:"Aircraft type"}],
  BANKING:[{id:"payment_terms",name:"Payment terms"},{id:"default_currency",name:"Contract currency"}],
  RENEWAL:[{id:"certificate_id",name:"Certificate reference"},{id:"contract_id",name:"Assigned contract ID"},{id:"requested_until",name:"Requested expiry date"}],
};
function OrgList({tenant,kind}:{tenant:string;kind:Kind}){
  const [search,setSearch]=useState("");const [offset,setOffset]=useState(0);
  const query=usePartnerLoad((signal)=>partnerRequest<Page<Record<string,unknown>>>(
    tenant,`organization/${kind}?limit=15&offset=${offset}&search=${encodeURIComponent(search)}`,{signal}),
    `${tenant}:${kind}:${offset}:${search}`);
  const page=query.value;
  return <Section title={label(kind)} action={<label className="partner-search">
      <span className="sr-only">Search {kind}</span>
      <input type="search" value={search} placeholder={`Search ${kind}`}
        onChange={event=>{setSearch(event.target.value);setOffset(0);}}/>
    </label>}>
    <State pending={query.pending} error={query.error} retry={query.reload} empty={!query.pending&&!query.error&&!page?.items.length}/>
    {page?.items.map((row,i)=><details className="partner-record" key={i}>
      <summary><strong>{String(row.site_name||row.contact_name||row.description||"Record")}</strong>
        <span>{String(row.site_code||row.assignment||row.capability_type||"View authorized detail")}</span></summary>
      <dl>{Object.entries(row).filter(([key])=>key!=="version").map(([key,value])=>
        <div key={key}><dt>{label(key)}</dt><dd>{value===null?"Not recorded":String(value)}</dd></div>)}</dl>
    </details>)}
    {page&&<Pager value={page} onChange={setOffset}/>}
  </Section>;
}
export default function PartnerOrganization({tenant,csrf,capabilities}:PartnerProps){
  const [kind,setKind]=useState<Kind>("sites");
  const [category,setCategory]=useState<Category>("IDENTITY");
  const [field,setField]=useState("trading_name");
  const [value,setValue]=useState("");
  const [reason,setReason]=useState("");
  const [busy,setBusy]=useState(false);const [message,setMessage]=useState("");const [error,setError]=useState("");
  const [offset,setOffset]=useState(0);
  const org=usePartnerLoad((signal)=>partnerRequest<Organization>(tenant,"organization",{signal}),tenant);
  const proposals=usePartnerLoad((signal)=>partnerRequest<Page<Change>>(tenant,
    `change-requests?limit=12&offset=${offset}`,{signal}),`${tenant}:${offset}`);
  const canPropose=capabilities.includes("profile.propose") && capabilities.includes("profile.read");
  const submit=(event:React.FormEvent)=>{
    event.preventDefault();setBusy(true);setMessage("");setError("");
    void partnerRequest(tenant,"change-requests",{
      method:"POST",csrf,body:{category,fields:{[field]:value.trim()},reason:reason.trim()},
    }).then(()=>{setMessage("Change proposal submitted for authorized review. Approved records were not overwritten.");
      setValue("");setReason("");proposals.reload();
    }).catch(x=>setError(x instanceof Error?x.message:"Request not accepted")).finally(()=>setBusy(false));
  };
  return <div className="partner-stack">
    <Section title="Registered organization" description="Authoritative Procurement and Quality records. Approved information is read-only until a reviewer applies a controlled change.">
      <State pending={org.pending} error={org.error} retry={org.reload}/>
      {org.value&&<>
        <dl className="partner-facts">{Object.entries(org.value.supplier).filter(([key])=>key!=="notes"&&key!=="approved_by_user_id").map(([key,v])=>
          <div key={key}><dt>{label(key)}</dt><dd>{String(v??"—")}</dd></div>)}</dl>
        <h3>Provider classifications</h3>
        <div className="partner-taglist">{org.value.roles.map(item=>
          <span key={item.role_code} className="partner-tag">{label(item.role_code)}</span>)}</div>
        {org.value.profile&&<p className="partner-muted">Approved scope: {String(org.value.profile.scope_summary||"See Compliance for formal approved categories.")} · Next review {friendlyDate(String(org.value.profile.next_review_due_on||""))}</p>}
      </>}
    </Section>
    <div className="partner-tabs" role="group" aria-label="Organization records">
      {(["sites","contacts","capabilities"] as Kind[]).map(x=>
        <button key={x} type="button" aria-pressed={kind===x} onClick={()=>setKind(x)}>{label(x)}</button>)}
    </div>
    <OrgList tenant={tenant} kind={kind}/>
    {canPropose&&<Section title="Propose an organization change" description="Submitted identity, site, contact, capability and commercial changes are never applied automatically.">
      <form className="partner-form" onSubmit={submit}>
        <label>Change category<select value={category} onChange={event=>{
          const next=event.target.value as Category;setCategory(next);setField(fields[next][0].id);setValue("");
        }}>{(Object.keys(fields) as Category[]).filter(x=>x!=="BANKING"||capabilities.includes("contract.read")).map(x=><option key={x} value={x}>{label(x)}</option>)}</select></label>
        <label>Information to update<select value={field} onChange={event=>setField(event.target.value)}>
          {fields[category].map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
        <label>Proposed value<input required maxLength={500} value={value} onChange={event=>setValue(event.target.value)}/></label>
        <label>Reason and supporting context<textarea required minLength={12} maxLength={2000} rows={3}
          value={reason} onChange={event=>setReason(event.target.value)}/></label>
        <ActionNotice value={error} error/><ActionNotice value={message}/>
        <button className="partner-primary" disabled={busy||!value.trim()||reason.trim().length<12}>
          {busy?"Submitting…":"Send for controlled review"}</button>
      </form>
    </Section>}
    <Section title="My change requests">
      <State pending={proposals.pending} error={proposals.error} retry={proposals.reload}
        empty={!proposals.pending&&!proposals.error&&!proposals.value?.items.length}/>
      {proposals.value?.items.map(row=><div className="partner-row" key={row.id}>
        <div><strong>{label(row.category)} change</strong><small>{row.reason}</small>
          {row.review_note&&<small>Reviewer: {row.review_note}</small>}</div>
        <Status value={row.status}/>
      </div>)}
      {proposals.value&&<Pager value={proposals.value} onChange={setOffset}/>}
    </Section>
  </div>;
}
