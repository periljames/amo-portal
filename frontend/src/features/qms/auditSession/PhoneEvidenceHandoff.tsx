import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { BarcodeFormat, QRCodeWriter } from '@zxing/library';
import { apiRequest, qmsPath } from '../../../services/apiClient';
import { listAuditEvidence } from '../../../services/qmsAuditEvidence';

export default function PhoneEvidenceHandoff({amoCode,auditId,itemId,question,onClose}:{amoCode:string;auditId:string;itemId:string;question:string;onClose:()=>void}){
 const [grant,setGrant]=useState<{token:string;expires_at:string}|null>(null);
 const [error,setError]=useState('');const [received,setReceived]=useState<string[]>([]);const [expired,setExpired]=useState(false);
 const [cells,setCells]=useState<{path:string;size:number}|null>(null);const dialog=useRef<HTMLDialogElement>(null);const cache=useQueryClient();
 useEffect(()=>{dialog.current?.showModal();},[]);
 useEffect(()=>{let active=true;
  apiRequest<{token:string;expires_at:string}>(qmsPath(amoCode,`/audits/${auditId}/checklist-items/${itemId}/phone-capture`),{method:'POST',headers:{'X-AMO-Silent-Error':'1'},offline:{queueMutation:false}}).then(value=>{if(active)setGrant(value);}).catch(e=>{if(active)setError(e instanceof Error?e.message:'Could not link phone. Try again when connected.');});
  return()=>{active=false;};
 },[amoCode,auditId,itemId]);
 const url=grant?`${location.origin}/qms/phone-capture#${grant.token}`:'';
 useEffect(()=>{if(!url)return;const matrix=new QRCodeWriter().encode(url,BarcodeFormat.QR_CODE,256,256,new Map()) as {get:(x:number,y:number)=>boolean;getWidth:()=>number;getHeight:()=>number};let path='';for(let y=0;y<matrix.getHeight();y++)for(let x=0;x<matrix.getWidth();x++)if(matrix.get(x,y))path+=`M${x} ${y}h1v1h-1z`;setCells({path,size:matrix.getWidth()});},[url]);
 useEffect(()=>{if(!grant)return;let active=true;let running=false;const seen=new Set<string>();const started=Date.parse(grant.expires_at)-601000;
  const poll=async()=>{if(running||!active)return;if(Date.now()>=Date.parse(grant.expires_at)){setExpired(true);return;}running=true;
   try{const result=await listAuditEvidence(amoCode,auditId,itemId);const photos=result.items.filter(row=>row.source_device_id==='paired-phone'&&Date.parse(row.created_at||'')>=started);const fresh=photos.filter(row=>!seen.has(row.id));
    if(active&&fresh.length){fresh.forEach(row=>seen.add(row.id));setReceived(photos.map(row=>row.filename));void cache.invalidateQueries({queryKey:['qms','live-audit-checklist',amoCode,auditId]});void cache.invalidateQueries({queryKey:['qms','audit-evidence',amoCode,auditId,itemId]});}
   }catch{/* Keep the code visible through temporary connection interruptions. */}finally{running=false;}
  };void poll();const timer=setInterval(()=>void poll(),3000);return()=>{active=false;clearInterval(timer);};
 },[grant,amoCode,auditId,itemId,cache]);
 return <dialog ref={dialog} className="audit-evidence-camera audit-phone-handoff" aria-label="Use phone camera" onCancel={onClose}>
  <header><h2>Use phone camera</h2><button type="button" onClick={onClose}>Done</button></header><p>{question}</p>
  {error?<p role="alert">{error}</p>:!grant?<p role="status">Creating phone link…</p>:expired?<p role="status">This link has expired. Close and generate a new QR code.</p>:<>
   <p>Scan with your phone camera. Photos attach to this question at their original resolution.</p>
   {cells?<svg width="256" height="256" viewBox={`0 0 ${cells.size} ${cells.size}`} role="img" aria-label="QR code for phone camera"><rect width={cells.size} height={cells.size} fill="white"/><path d={cells.path} fill="black"/></svg>:null}
   <p><small>Link expires in 10 minutes. Your phone must be able to reach this portal.</small></p><a href={url} target="_blank" rel="noreferrer">Open phone capture page</a>
  </>}
  <div role="status">{received.length?`${received.length} photo${received.length===1?'':'s'} received`:'Waiting for photos…'}</div>{received.length?<ul>{received.map((name,i)=><li key={`${name}-${i}`}>{name}</li>)}</ul>:null}
 </dialog>;
}
