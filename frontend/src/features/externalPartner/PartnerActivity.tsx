import React,{useEffect,useState} from "react";
import {Link} from "react-router-dom";
import type {PartnerProps} from "./ExternalPartnerPage";
import {friendlyDate,partnerRequest,type Notification,type Page} from "./partnerApi";
import {ActionNotice,Pager,Section,State,Status} from "./PartnerPrimitives";
import { usePartnerLoad } from "./usePartnerLoad";
type Event={id:string;event_type:string;occurred_at:string};
type AlertPreferences={revision:number;in_app_enabled:boolean;email_enabled:boolean;digest_enabled:boolean};
type AlertAction={event_key:string;link:string;acknowledged_at:string|null};
const destination:Record<string,string>={CHANGE:"organization",CONTRACT:"contracts",CAR:"quality",EVIDENCE:"compliance",QUALIFICATION:"qualification",RESTRICTION:"qualification"};
export default function PartnerActivity({tenant,csrf}:PartnerProps){
  const [offset,setOffset]=useState(0);const [historyOffset,setHistoryOffset]=useState(0);
  const [unreadOnly,setUnreadOnly]=useState(false);
  const [busy,setBusy]=useState("");const [notice,setNotice]=useState("");const [error,setError]=useState("");
  const [preferences,setPreferences]=useState<AlertPreferences|null>(null);
  const [actionLinks,setActionLinks]=useState<Record<string,AlertAction>>({});
  useEffect(()=>{
    let active=true;
    void partnerRequest<AlertPreferences>(tenant,"alert-preferences").then(value=>{
      if(active)setPreferences(value);
    }).catch(()=>{if(active)setError("Provider notification preferences could not be loaded.");});
    return()=>{active=false;};
  },[tenant]);
  const savePreferences=()=>{
    if(!preferences)return;
    setBusy("preferences");setError("");setNotice("");
    void partnerRequest<AlertPreferences>(tenant,"alert-preferences",{
      method:"PUT",csrf,body:preferences,
    }).then(()=>{
      setNotice("Notification preferences saved.");
      return partnerRequest<AlertPreferences>(tenant,"alert-preferences");
    }).then(setPreferences)
      .catch(e=>setError(e instanceof Error?e.message:"Preferences could not be saved"))
      .finally(()=>setBusy(""));
  };
  const resolveAction=(id:string)=>{
    setBusy(id);setError("");
    void partnerRequest<AlertAction>(tenant,"alert-preferences/actions/"+encodeURIComponent(id))
      .then(value=>setActionLinks(prev=>({...prev,[id]:value})))
      .catch(e=>setError(e instanceof Error?e.message:"Assigned action not available"))
      .finally(()=>setBusy(""));
  };
  const acknowledgeAction=(id:string)=>{
    setBusy(id);setError("");
    void partnerRequest(tenant,"alert-preferences/actions/"+encodeURIComponent(id)+"/acknowledge",{
      method:"POST",csrf,body:{},
    }).then(()=>{
      setNotice("Provider action acknowledged.");
      notifications.reload();
    }).catch(e=>setError(e instanceof Error?e.message:"Acknowledgement failed"))
      .finally(()=>setBusy(""));
  };
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
    <Section title="My notification preferences"
      description="These choices apply only to this signed-in provider member, not your tenant or other users.">
      {preferences?<div className="partner-stack">
        <label><input type="checkbox" checked={preferences.in_app_enabled}
          onChange={e=>setPreferences({...preferences,in_app_enabled:e.target.checked})}/>
          In-app reminders</label>
        <label><input type="checkbox" checked={preferences.email_enabled}
          onChange={e=>setPreferences({...preferences,email_enabled:e.target.checked})}/>
          Email preference (used only for supported verified provider channels)</label>
        <label><input type="checkbox" checked={preferences.digest_enabled}
          onChange={e=>setPreferences({...preferences,digest_enabled:e.target.checked})}/>
          Digest preference</label>
        <button disabled={busy==="preferences"} onClick={savePreferences}>Save preferences</button>
      </div>:<p>Loading member preferences…</p>}
    </Section>
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
          {row.resource_kind==="PROVIDER_ALERT"&&row.resource_id&&<>
            {!actionLinks[row.resource_id]?<button type="button"
              onClick={()=>resolveAction(row.resource_id!)} disabled={busy===row.resource_id}>
              Open assigned action</button>:<>
              <Link to={actionLinks[row.resource_id].link}>Open assigned work →</Link>
              {!actionLinks[row.resource_id].acknowledged_at&&<button type="button"
                disabled={busy===row.resource_id}
                onClick={()=>acknowledgeAction(row.resource_id!)}>Acknowledge action</button>}
            </>}
          </>}
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
