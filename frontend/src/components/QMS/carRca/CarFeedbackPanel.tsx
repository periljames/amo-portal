import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiRequest, qmsPath } from "../../../services/apiClient";
import { getApiBaseUrl } from "../../../services/config";
import "./car-feedback.css";

type Entry = { id:string; message:string; actor_name:string; actor_kind:string; visibility:string; created_at:string };
type Feed = { car_id:string; status:string; root_cause_status:string; capa_status:string; items:Entry[]; next_cursor:string|null };
type Props = { amoCode?:string; carId:string; token?:string; actorName?:string; canWrite?:boolean; onUpdate?:()=>Promise<void> };

export default function CarFeedbackPanel({amoCode,carId,token,actorName,canWrite=true,onUpdate}:Props) {
  const queryClient = useQueryClient();
  const [feed,setFeed]=useState<Feed|null>(null), [items,setItems]=useState<Entry[]>([]);
  const [text,setText]=useState(""), [internal,setInternal]=useState(false), [busy,setBusy]=useState(false);
  const [error,setError]=useState(""), [live,setLive]=useState(false), [message,setMessage]=useState("");
  const callback=useRef(onUpdate); callback.current=onUpdate;
  const pending=useRef<{id:string;text:string;internal:boolean}|null>(null);
  const signature=useRef("");
  const olderLoaded=useRef(false);
  const list=useRef<HTMLOListElement>(null), followLatest=useRef(true);
  const refresh=useRef<()=>Promise<void>>(async()=>undefined);
  const path=token ? `/quality/cars/invite/${encodeURIComponent(token)}/feedback` : qmsPath(amoCode||"",`/cars/${encodeURIComponent(carId)}/feedback`);
  async function request<T>(suffix="",body?:unknown):Promise<T> {
    if(!token) return apiRequest<T>(path+suffix,{method:body===undefined?"GET":"POST",body:body===undefined?undefined:JSON.stringify(body),cacheTtlMs:0,persistCache:false,staleWhileOfflineMs:0,headers:{"X-AMO-Silent-Error":"1"}});
    const response=await fetch(getApiBaseUrl()+path+suffix,{method:body===undefined?"GET":"POST",cache:"no-store",credentials:"omit",
      headers:{Accept:"application/json",...(body===undefined?{}:{"Content-Type":"application/json"})},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
    if(!response.ok) {const data=await response.json().catch(()=>null);throw new Error(typeof data?.detail==="string"?data.detail:`Feedback unavailable (${response.status}).`);}
    return response.json() as Promise<T>;
  }
  const requestRef=useRef(request); requestRef.current=request;
  useEffect(()=>{if(followLatest.current&&list.current)list.current.scrollTop=list.current.scrollHeight;},[items]);
  useEffect(()=>{
    let active=true, loading=false;
    signature.current="";olderLoaded.current=false;followLatest.current=true;setFeed(null);setItems([]);setError("");setText("");pending.current=null;
    const load=async()=>{
      if(loading || document.visibilityState==="hidden") return;
      loading=true;
      try {
        const data=await requestRef.current<Feed>();
        if(!Array.isArray(data.items)||data.car_id!==carId) throw new Error("The server returned an invalid CAR feedback record.");
        if(!active)return;
        const next=JSON.stringify([data.status,data.root_cause_status,data.capa_status,data.items[0]?.id]);
        const changed=Boolean(signature.current && signature.current!==next);
        signature.current=next;setFeed(previous=>({...data,next_cursor:olderLoaded.current?previous?.next_cursor||null:data.next_cursor}));setLive(true);
        // GET/SSE refresh does not acknowledge an ambiguous POST. Preserve the
        // send failure until the exact idempotent message is retried and confirmed.
        if(!pending.current)setError("");
        setItems(previous=>Array.from(new Map([...previous,...data.items].map(item=>[item.id,item])).values()).sort((a,b)=>a.created_at.localeCompare(b.created_at)||a.id.localeCompare(b.id)));
        if(changed) {
          setMessage("New feedback or review decision received.");
          window.dispatchEvent(new CustomEvent("amo:car-feedback-updated",{detail:{carId}}));
          if(!token) void queryClient.invalidateQueries({predicate:q=>q.queryKey.some(key=>typeof key==="string"&&key.startsWith("qms-car"))});
          await callback.current?.();
        }
      } catch(cause) {if(active){setLive(false);setError(cause instanceof Error?cause.message:"Feedback could not be refreshed. Your message is retained.");}}
      finally {loading=false;}
    };
    refresh.current=load;void load();
    const interval=window.setInterval(()=>void load(),5000);
    const visible=()=>void load();window.addEventListener("focus",visible);document.addEventListener("visibilitychange",visible);
    const stream=token?new EventSource(getApiBaseUrl()+path+"/events"):null;
    if(stream){stream.onmessage=()=>void load();stream.addEventListener("access-ended",()=>{stream.close();setLive(false);void load();});}
    return()=>{active=false;window.clearInterval(interval);window.removeEventListener("focus",visible);document.removeEventListener("visibilitychange",visible);stream?.close();};
  },[carId,path,token,queryClient]);
  async function send() {
    if(!text.trim()||busy)return;
    setBusy(true);setError("");
    if(!pending.current||pending.current.text!==text.trim()||pending.current.internal!==internal)pending.current={id:crypto.randomUUID(),text:text.trim(),internal};
    try {
      await request("",{message:pending.current.text,client_message_id:pending.current.id,actor_name:actorName?.trim()||"Invited respondent",visibility:internal&&!token?"INTERNAL":"SHARED"});
      setText("");pending.current=null;setMessage(internal&&!token?"Internal note recorded.":"Feedback sent and retained in CAR history.");await refresh.current();
    }catch(cause){setError(cause instanceof Error?cause.message:"Feedback was not confirmed. Retry; your text is retained.");}
    finally{setBusy(false);}
  }
  async function earlier() {
    if(!feed?.next_cursor||busy)return;setBusy(true);
    try{const data=await request<Feed>(`?before=${encodeURIComponent(feed.next_cursor)}`);olderLoaded.current=true;followLatest.current=false;setItems(previous=>Array.from(new Map([...data.items,...previous].map(item=>[item.id,item])).values()).sort((a,b)=>a.created_at.localeCompare(b.created_at)||a.id.localeCompare(b.id)));setFeed(current=>current?{...current,next_cursor:data.next_cursor}:current);}
    catch(cause){setError(cause instanceof Error?cause.message:"Earlier history unavailable.");}finally{setBusy(false);}
  }
  const closed=feed?.status==="CLOSED"||feed?.status==="CANCELLED";
  return <section className="car-feedback" aria-label="CAR feedback and decision history">
    <header><h2>Feedback & decision history</h2><span role="status">{live?"Live updates":"Reconnecting…"}</span></header>
    {error&&<p role="alert">{error} <button type="button" onClick={()=>void refresh.current()}>Retry feedback</button></p>}
    {message&&<p role="status">{message}</p>}
    {items.length>0&&<button type="button" onClick={()=>{followLatest.current=true;if(list.current)list.current.scrollTop=list.current.scrollHeight;}}>Latest feedback</button>}
    {feed?.next_cursor&&<button type="button" disabled={busy} onClick={()=>void earlier()}>Load earlier history</button>}
    <ol ref={list} onScroll={event=>{const element=event.currentTarget;followLatest.current=element.scrollHeight-element.scrollTop-element.clientHeight<32;}} aria-label="Retained CAR communication">{items.map(item=><li key={item.id}>
      <div><strong>{item.actor_name}</strong><span>{item.actor_kind==="AUDITEE"?"Auditee":item.actor_kind==="SYSTEM"?"System":"Quality / staff"}{item.visibility==="INTERNAL"?" · Internal only":" · Shared"}</span><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString(undefined,{timeZoneName:"short"})}</time></div>
      <p>{item.message}</p>
    </li>)}</ol>
    {feed&&!items.length&&<p>No shared feedback or decisions yet.</p>}
    {closed?<p>CAR closed · communication history is read only.</p>:canWrite&&<div className="car-feedback__compose">
      <label>Message to {token?"the audit team":"the auditee"}<textarea aria-label="CAR feedback message" rows={3} maxLength={4000} value={text} disabled={busy} onChange={event=>setText(event.target.value)}/></label>
      {!token&&<label className="car-feedback__private"><input type="checkbox" checked={internal} disabled={busy} onChange={event=>setInternal(event.target.checked)}/>Internal note · hidden from auditee</label>}
      <div><small>{text.length}/4000 · {internal&&!token?"Only staff can read this note.":"Shared with the CAR respondent."}</small><button type="button" disabled={busy||!text.trim()||!feed} onClick={()=>void send()}>{busy?"Sending…":internal&&!token?"Record internal note":"Send feedback"}</button></div>
    </div>}
  </section>;
}
