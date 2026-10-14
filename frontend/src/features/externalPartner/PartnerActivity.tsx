import React,{useState} from "react";
import {Link} from "react-router-dom";
import type {PartnerProps} from "./ExternalPartnerPage";
import {friendlyDate,partnerRequest,type Notification,type Page} from "./partnerApi";
import {ActionNotice,Pager,Section,State,Status,usePartnerLoad} from "./PartnerPrimitives";
type Event={id:string;event_type:string;occurred_at:string};
const destination:Record<string,string>={CHANGE:"organization",CONTRACT:"contracts",CAR:"quality",EVIDENCE:"compliance",QUALIFICATION:"qualification",RESTRICTION:"qualification"};
export default function PartnerActivity({tenant,csrf}:PartnerProps){
  const [offset,setOffset]=useState(0);const [historyOffset,setHistoryOffset]=useState(0);
  const [unreadOnly,setUnreadOnly]=useState(false);
  const [busy,setBusy]=useState("");const [notice,setNotice]=useState("");const [error,setError]=useState("");
  const notifications=usePartnerLoad((signal)=>partnerRequest<Page<Notification>>(tenant,
    `notifications?limit=20&offset=${offset}&unread_only=${unreadOnly}`,{signal}),
    `${tenant}:${offset}:${unreadOnly}`);
  const history=usePartnerLoad((signal)=>partnerRequest<Page<Event>>(tenant,
    `activity?limit=15&offset=${historyOffset}`,{signal}),
    `${tenant}:events:${historyOffset}`);
  const read=(id:string)=>{
    setBusy(id);setError("");setNotice("");
    void partnerRequest(tenant,`notifications/${encodeURIComponent(id)}/read`,{
      method:"POST",csrf,body:{},
    }).then(()=>{setNotice("Notification marked as read.");notifications.reload();})
      .catch(e=>setError(e instanceof Error?e.message:"Read state could not be saved"))
      .finally(()=>setBusy(""));
  };
  return <div className="partner-stack">
    <Section title="Provider notifications"
      description="Attributable account, submission, agreement and Quality review events from the server."
      action={<label className="partner-check"><input type="checkbox" checked={unreadOnly}
        onChange={e=>{setUnreadOnly(e.target.checked);setOffset(0);}}/>Unread only</label>}>
      <State pending={notifications.pending} error={notifications.error} retry={notifications.reload}
        empty={!notifications.pending&&!notifications.error&&!notifications.value?.items.length}/>
      {notifications.value?.items.map(row=><div key={row.id} className="partner-notification"
        data-unread={!row.read_at}>
        <div><small>{row.category} · {friendlyDate(row.created_at)}</small><strong>{row.title}</strong>
          <p>{row.message}</p>
          {row.resource_kind&&destination[row.resource_kind]&&<Link to={`/partner/${tenant}/${destination[row.resource_kind]}`}>Open related workspace →</Link>}
        </div>
        <div>{row.read_at?<Status value="READ"/>:
          <button type="button" disabled={busy===row.id} onClick={()=>read(row.id)}>
            {busy===row.id?"Saving…":"Mark read"}</button>}</div>
      </div>)}
      <ActionNotice value={error} error/><ActionNotice value={notice}/>
      {notifications.value&&<Pager value={notifications.value} onChange={setOffset}/>}
    </Section>
    <Section title="My accountable security and access history"
      description="Recent activity for this external identity and tenant grant. Internal staff identifiers are not disclosed.">
      <State pending={history.pending} error={history.error} retry={history.reload}
        empty={!history.pending&&!history.error&&!history.value?.items.length}/>
      {history.value?.items.map(row=><div className="partner-row" key={row.id}>
        <strong>{row.event_type.replaceAll("_"," ")}</strong><small>{friendlyDate(row.occurred_at)}</small>
      </div>)}
      {history.value&&<Pager value={history.value} onChange={setHistoryOffset}/>}
    </Section>
  </div>;
}
