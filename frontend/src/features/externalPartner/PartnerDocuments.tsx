import React,{useEffect,useRef,useState} from "react";
import type {PartnerProps} from "./ExternalPartnerPage";
import PublicationDocxLayoutViewer from "../../pages/manuals/PublicationDocxLayoutViewer";
import {friendlyDate,label,partnerRequest,partnerUrl,type Contract,type Page} from "./partnerApi";
import {ActionNotice,Section,State,Status,usePartnerLoad} from "./PartnerPrimitives";

type Requirement={id:string;code:string;title:string;description:string;mandatory:boolean;
  expiry_required:boolean;acknowledgement_required:boolean;acknowledged_by_me:boolean;
  reminder_days:number;form_manual_id:string|null;form_revision_id:string|null;
  form_available:boolean;version:number};
type Submission={id:string;filename:string;evidence_type:string;status:string;
  requirement_id:string|null;related_kind:string;related_id:string|null;
  supersedes_submission_id:string|null;form_revision_id:string|null;
  valid_until:string|null;created_at:string;review_note:string|null;
  qms_evidence_id:string|null;dms_revision_id:string|null;sha256:string};
type ResponsePage={items:Submission[];limit:number;offset:number;has_more:boolean};

function saveBlob(blob:Blob,filename:string){
  const url=URL.createObjectURL(blob);
  const link=document.createElement("a");link.href=url;link.download=filename;
  document.body.appendChild(link);link.click();link.remove();
  window.setTimeout(()=>URL.revokeObjectURL(url),2000);
}
export default function PartnerDocuments({tenant,csrf,capabilities}:PartnerProps){
  const [refresh,setRefresh]=useState(0);const [offset,setOffset]=useState(0);
  const [requirementId,setRequirementId]=useState("");
  const [file,setFile]=useState<File|null>(null);
  const [related,setRelated]=useState("PROVIDER");const [relatedId,setRelatedId]=useState("");
  const [supersedes,setSupersedes]=useState("");const [validUntil,setValidUntil]=useState("");
  const [busy,setBusy]=useState(false);const [progress,setProgress]=useState(0);
  const [notice,setNotice]=useState("");const [error,setError]=useState("");
  const [acknowledgeCheckedId,setAcknowledgeCheckedId]=useState("");
  const [acknowledging,setAcknowledging]=useState("");
  const [preview,setPreview]=useState<{url:string;blob:Blob;name:string;mime:string}|null>(null);
  const [previewText,setPreviewText]=useState("");
  const previewUrl=useRef("");
  const pendingKey=useRef("");const xhrRef=useRef<XMLHttpRequest|null>(null);
  const resumableAbort=useRef<AbortController|null>(null);
  const requirements=usePartnerLoad((signal)=>partnerRequest<{items:Requirement[]}>(tenant,
    "documents/requirements",{signal}),`${tenant}:${refresh}`);
  const submissions=usePartnerLoad((signal)=>partnerRequest<ResponsePage>(tenant,
    `documents/submissions?limit=25&offset=${offset}`,{signal}),`${tenant}:${offset}:${refresh}`);
  const assignments=usePartnerLoad((signal)=>partnerRequest<{items:{id:string}[]}>(tenant,
    "documents/assignment-scopes",{signal}),`${tenant}:${refresh}:assignments`);
  const contracts=usePartnerLoad((signal)=>capabilities.includes("contract.read")?
    partnerRequest<Page<Contract>>(tenant,"contracts?limit=50",{signal}):
    Promise.resolve({items:[],limit:50,offset:0,has_more:false}),`${tenant}:${refresh}`);
  const rfqs=usePartnerLoad((signal)=>capabilities.includes("procurement.read")?
    partnerRequest<{items:{id:number;rfq_number:string}[]}>(tenant,"commerce/rfqs",{signal}):
    Promise.resolve({items:[] as {id:number;rfq_number:string}[]}),tenant+":rfqDocs:"+refresh);
  const orders=usePartnerLoad((signal)=>capabilities.includes("procurement.read")?
    partnerRequest<{items:{id:number;po_number:string}[]}>(tenant,"commerce/purchase-orders",{signal}):
    Promise.resolve({items:[] as {id:number;po_number:string}[]}),tenant+":poDocs:"+refresh);
  const shipments=usePartnerLoad((signal)=>capabilities.includes("procurement.read")?
    partnerRequest<{items:{id:string;po_id:number;shipment_reference:string}[]}>(tenant,"commerce/shipments",{signal}):
    Promise.resolve({items:[] as {id:string;po_id:number;shipment_reference:string}[]}),tenant+":shipmentDocs:"+refresh);
  const maintenance=usePartnerLoad((signal)=>capabilities.includes("task.read")?
    partnerRequest<{items:{id:string;work_number:string;work_title:string}[]}>(tenant,"maintenance-work",{signal}):
    Promise.resolve({items:[] as {id:string;work_number:string;work_title:string}[]}),tenant+":maintenanceDocs:"+refresh);
  useEffect(()=>()=>{xhrRef.current?.abort();resumableAbort.current?.abort();
    if(previewUrl.current)URL.revokeObjectURL(previewUrl.current);},[]);
  const current=requirements.value?.items.find(r=>r.id===requirementId);
  const prior=(submissions.value?.items||[]).filter(s=>s.requirement_id===requirementId &&
     s.related_kind===related && (s.related_id||"")===(relatedId||""));
  const supersededIds=new Set((submissions.value?.items||[]).map(s=>s.supersedes_submission_id).filter(Boolean));

  async function readOriginal(path:string,filename:string){
    setError("");setNotice("");
    try{
      const response=await fetch(partnerUrl(tenant,path),{credentials:"include",cache:"no-store"});
      if(!response.ok)throw new Error(`Document reader access denied (${response.status})`);
      const blob=await response.blob();
      if(previewUrl.current)URL.revokeObjectURL(previewUrl.current);
      const url=URL.createObjectURL(blob);previewUrl.current=url;
      const mime=blob.type||response.headers.get("Content-Type")||"";
      setPreview({url,blob,name:filename,mime});
      setPreviewText(mime.includes("text/plain")?await blob.text():"");
    }catch(e){setError(e instanceof Error?e.message:"Unable to read document");}
  }
  async function getOriginal(path:string,filename:string){
    setError("");setNotice("");
    try{
      const response=await fetch(partnerUrl(tenant,path),{credentials:"include",cache:"no-store"});
      if(!response.ok)throw new Error(`Controlled file access denied (${response.status})`);
      const mime=response.headers.get("Content-Type")||"";
      const ext=mime.includes("wordprocessingml")?".docx":mime.includes("application/pdf")?".pdf":
        mime.includes("image/png")?".png":mime.includes("image/jpeg")?".jpg":mime.includes("text/plain")?".txt":"";
      const resolved=/\\.[a-z0-9]{2,5}$/i.test(filename)?filename:filename+ext;
      saveBlob(await response.blob(),resolved);
    }catch(e){setError(e instanceof Error?e.message:"File could not be downloaded");}
  }
  async function acknowledgeForm(item:Requirement){
    if(acknowledgeCheckedId!==item.id||!item.form_available){setError("Open the granted form and confirm the declaration.");return;}
    setAcknowledging(item.id);setError("");setNotice("");
    try{
      await partnerRequest(tenant,`documents/requirements/${encodeURIComponent(item.id)}/acknowledge`,{
        method:"POST",csrf,body:{accepted:true,declaration:
          "I confirm that I have read and understood the controlled form identified by this exact published revision."},
      });
      setAcknowledgeCheckedId("");setNotice("Read-and-understood acknowledgement recorded for the exact form revision.");
      setRefresh(v=>v+1);
    }catch(e){setError(e instanceof Error?e.message:"Acknowledgement was not recorded");}
    finally{setAcknowledging("");}
  }
  async function largeUpload(selected:File,policy:Requirement,key:string){
    const controller=new AbortController();resumableAbort.current=controller;
    const storageKey=`provider-resumable:${tenant}`;
    setBusy(true);setProgress(0);setError("");setNotice("");
    try{
      const ext=selected.name.split(".").pop()?.toLowerCase()||"";
      const mime=selected.type||({
        pdf:"application/pdf",docx:"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        png:"image/png",jpg:"image/jpeg",jpeg:"image/jpeg",txt:"text/plain"
      } as Record<string,string>)[ext];
      if(!mime||selected.size>512*1024*1024)throw new Error("Maximum supported resumable file size is 512 MiB.");
      const signature=`${selected.name}:${selected.size}:${selected.lastModified}:${policy.id}:${related}:${relatedId}:${supersedes}:${validUntil}`;
      const remembered=(()=>{try{return JSON.parse(localStorage.getItem(storageKey)||"null") as
        {signature:string;retryKey:string}|null;}catch{return null;}})();
      const retryKey=remembered?.signature===signature?remembered.retryKey:key;
      pendingKey.current=retryKey;
      const started=await partnerRequest<{id:string;state:string;chunk_size:number;
        completed_submission_id:string|null}>(tenant,"documents/uploads",{
        method:"POST",csrf,signal:controller.signal,body:{
          filename:selected.name,content_type:mime,size_bytes:selected.size,
          requirement_id:policy.id,related_kind:related,related_id:related==="PROVIDER"?null:relatedId,
          supersedes_submission_id:supersedes||null,valid_until:validUntil||null,retry_key:retryKey,
        },
      });
      try{localStorage.setItem(storageKey,JSON.stringify({signature,retryKey}));}catch{/* private browser */}
      if(started.state!=="COMPLETED"){
        const state=await partnerRequest<{part_numbers:number[];bytes_received:number}>(
          tenant,`documents/uploads/${encodeURIComponent(started.id)}`,{signal:controller.signal});
        const received=new Set(state.part_numbers);
        setProgress(Math.floor(state.bytes_received*100/selected.size));
        const total=Math.ceil(selected.size/started.chunk_size);
        for(let index=0;index<total;index++){
          if(controller.signal.aborted)throw new DOMException("Transfer cancelled","AbortError");
          if(received.has(index))continue;
          const slice=selected.slice(index*started.chunk_size,
            Math.min(selected.size,(index+1)*started.chunk_size));
          const response=await fetch(partnerUrl(tenant,`documents/uploads/${started.id}/parts/${index}`),{
            method:"PUT",credentials:"include",signal:controller.signal,
            headers:{"X-External-CSRF":csrf,"Content-Type":"application/octet-stream"},body:slice,
          });
          if(!response.ok){
            const details=await response.json().catch(()=>({detail:"Part upload rejected"})) as {detail?:string};
            throw new Error(details.detail||`Part ${index+1} rejected (${response.status})`);
          }
          setProgress(Math.floor(Math.min(99,(index+1)*started.chunk_size/selected.size*100)));
        }
        await partnerRequest(tenant,`documents/uploads/${started.id}/complete`,{
          method:"POST",csrf,signal:controller.signal,
        });
      }
      if(controller.signal.aborted)return;
      try{localStorage.removeItem(storageKey);}catch{/* private browser */}
      pendingKey.current="";setFile(null);setSupersedes("");setValidUntil("");
      setProgress(100);setNotice("Original assembled, checksum-verified and scanned. Controlled Quality review is pending.");
      setRefresh(v=>v+1);
    }catch(e){
      if(controller.signal.aborted)setError("Upload cancelled. Reselect the same file to resume the saved chunks.");
      else setError((e instanceof Error?e.message:"Upload failed")+
        " Reselect the same file and retry to resume existing verified chunks.");
    }finally{resumableAbort.current=null;setBusy(false);}
  }
  function upload(e:React.FormEvent){
    e.preventDefault();
    if(!file||!current||busy)return;
    if(current.acknowledgement_required&&!current.acknowledged_by_me){
      setError("Acknowledge the current controlled form before uploading this document.");return;
    }
    if(!pendingKey.current)pendingKey.current=crypto.randomUUID().replace(/-/g,"");
    if(file.size>20*1024*1024){void largeUpload(file,current,pendingKey.current);return;}
    const key=pendingKey.current;
    const xhr=new XMLHttpRequest();xhrRef.current=xhr;
    setBusy(true);setError("");setNotice("");setProgress(0);
    xhr.open("POST",partnerUrl(tenant,"documents/submissions"));xhr.withCredentials=true;
    xhr.setRequestHeader("X-External-CSRF",csrf);
    xhr.upload.onprogress=event=>{if(event.lengthComputable)setProgress(Math.round(event.loaded*100/event.total));};
    xhr.onerror=()=>{setError("Connection interrupted. Retry with the same file to avoid a duplicate.");
      setBusy(false);xhrRef.current=null;};
    xhr.onabort=()=>{setError("Transfer cancelled. No submission confirmation was received.");
      setBusy(false);xhrRef.current=null;};
    xhr.onload=()=>{
      const result=(()=>{try{return JSON.parse(xhr.responseText) as {detail?:string;filename?:string};}
        catch{return {};}})();
      if(xhr.status>=200&&xhr.status<300){
        setNotice(`${result.filename||file.name} is in controlled review. Submission does not approve this provider.`);
        pendingKey.current="";setFile(null);setSupersedes("");setValidUntil("");setProgress(100);
        setRefresh(v=>v+1);
      }else setError(result.detail||`Upload rejected (${xhr.status}). Retry after correction.`);
      setBusy(false);xhrRef.current=null;
    };
    const payload=new FormData();
    payload.append("file",file);payload.append("requirement_id",requirementId);
    payload.append("related_kind",related);
    payload.append("related_id",related==="PROVIDER"?"":relatedId);
    payload.append("supersedes_submission_id",supersedes);
    payload.append("idempotency_key",key);
    if(validUntil)payload.append("valid_until",validUntil);
    xhr.send(payload);
  }
  const refreshAll=()=>setRefresh(v=>v+1);
  const resetRetry=()=>{pendingKey.current="";setProgress(0);
    try{localStorage.removeItem(`provider-resumable:${tenant}`);}catch{/* private browser */}
  };
  return <div className="partner-stack">
    <Section title="Required documents and approved forms"
      description="Your AMO controls these requirements by provider category. Only documents released to your account are downloadable.">
      <State pending={requirements.pending} error={requirements.error} retry={requirements.reload}/>
      {!requirements.value?.items.length&&<p className="partner-empty">No document requirements have been configured for your provider category. Contact Quality before sending files.</p>}
      {requirements.value?.items.map(r=><div key={r.id} className="partner-row">
        <div><strong>{r.title}{r.mandatory?" · Required":""}</strong>
          <small>{r.code} · Policy version {r.version}{r.expiry_required?" · Expiry date required":""}</small>
          {r.description&&<small>{r.description}</small>}
          {r.acknowledgement_required&&<small>Form acknowledgement:
            {r.acknowledged_by_me?" Recorded for this revision":" Required before submission"}</small>}
          {r.form_revision_id&&<small>Approved form revision: {r.form_revision_id}</small>}
        </div><div className="partner-buttons">
          {r.form_available&&<button type="button" onClick={()=>void readOriginal(
            `documents/requirements/${encodeURIComponent(r.id)}/form`,`${r.code}-approved-form`)}>
            Read current form</button>}
          {r.form_available&&<button type="button" onClick={()=>void getOriginal(
            `documents/requirements/${encodeURIComponent(r.id)}/form`,`${r.code}-approved-form`)}>
            Download current form</button>}
          {!r.form_available&&r.form_revision_id&&<small>Form access not granted</small>}
          {r.acknowledgement_required&&!r.acknowledged_by_me&&r.form_available&&<div>
            <label><input type="checkbox" checked={acknowledgeCheckedId===r.id}
              onChange={e=>setAcknowledgeCheckedId(e.target.checked?r.id:"")}/>
              I have opened, read and understood the controlled form revision shown.</label>
            <button type="button" disabled={acknowledgeCheckedId!==r.id||acknowledging===r.id}
              onClick={()=>void acknowledgeForm(r)}>
              {acknowledging===r.id?"Recording…":"Record read-and-understood acknowledgement"}</button>
          </div>}
        </div>
      </div>)}
    </Section>
    {capabilities.includes("document.submit")&&<Section title="Submit a controlled response"
      description="PDF, DOCX, JPEG, PNG or UTF-8 text (up to 512 MiB). Large originals transfer in recoverable 8 MiB chunks. Quality review remains separate.">
      <form className="partner-form" onSubmit={upload}>
        <label>Requirement
          <select required value={requirementId} onChange={e=>{setRequirementId(e.target.value);setSupersedes("");resetRetry();}}>
            <option value="">Select a document requirement</option>
            {requirements.value?.items.map(r=><option key={r.id} value={r.id}>{r.title}</option>)}
          </select></label>
        <label>Linked scope<select value={related} onChange={e=>{setRelated(e.target.value);setRelatedId("");setSupersedes("");resetRetry();}}>
          <option value="PROVIDER">Provider-level record</option>
          {contracts.value?.items.length?<option value="CONTRACT">Assigned agreement</option>:null}
          {assignments.value?.items.length?<option value="ASSIGNMENT">Assigned audit or QMS work</option>:null}
          {rfqs.value?.items.length?<option value="RFQ">Procurement RFQ</option>:null}
          {orders.value?.items.length?<option value="PO">Issued purchase order</option>:null}
          {shipments.value?.items.length?<option value="SHIPMENT">Advance shipment notice</option>:null}
          {maintenance.value?.items.length?<option value="CONTRACTED_WORK">Assigned contracted maintenance work</option>:null}
        </select></label>
        {related==="CONTRACT"&&<label>Assigned agreement<select required value={relatedId} onChange={e=>{setRelatedId(e.target.value);setSupersedes("");resetRetry();}}>
          <option value="">Choose assigned agreement</option>
          {contracts.value?.items.map(c=><option key={c.id} value={c.id}>{c.contract_number} · {c.title}</option>)}
        </select></label>}
        {related==="ASSIGNMENT"&&<label>Assigned audit<select required value={relatedId}
          onChange={e=>{setRelatedId(e.target.value);setSupersedes("");resetRetry();}}>
          <option value="">Choose authorized audit assignment</option>
          {assignments.value?.items.map(a=><option key={a.id} value={a.id}>{a.id}</option>)}
        </select></label>}
        {related==="RFQ"&&<label>Invited RFQ<select required value={relatedId} onChange={e=>{setRelatedId(e.target.value);setSupersedes("");resetRetry();}}>
          <option value="">Select RFQ (explicit member document scope required)</option>
          {rfqs.value?.items.map(x=><option key={x.id} value={x.id}>{x.rfq_number}</option>)}
        </select></label>}
        {related==="PO"&&<label>Issued PO<select required value={relatedId} onChange={e=>{setRelatedId(e.target.value);setSupersedes("");resetRetry();}}>
          <option value="">Select PO (explicit member document scope required)</option>
          {orders.value?.items.map(x=><option key={x.id} value={x.id}>{x.po_number}</option>)}
        </select></label>}
        {related==="SHIPMENT"&&<label>Advance shipment notice<select required value={relatedId} onChange={e=>{setRelatedId(e.target.value);setSupersedes("");resetRetry();}}>
          <option value="">Select shipment (issued PO document scope required)</option>
          {shipments.value?.items.map(x=><option key={x.id} value={x.id}>{x.shipment_reference}</option>)}
        </select></label>}
        {related==="CONTRACTED_WORK"&&<label>Authorized contracted work<select required value={relatedId} onChange={e=>{setRelatedId(e.target.value);setSupersedes("");resetRetry();}}>
          <option value="">Choose your assigned work order</option>
          {maintenance.value?.items.map(x=><option key={x.id} value={x.id}>{x.work_number} · {x.work_title}</option>)}
        </select></label>}
        <label>Replace earlier submission (optional)<select value={supersedes} onChange={e=>{setSupersedes(e.target.value);resetRetry();}}>
          <option value="">First submission</option>
          {prior.map(s=><option key={s.id} value={s.id}>{s.filename} · {label(s.status)} · {friendlyDate(s.created_at)}</option>)}
        </select></label>
        <label>Evidence expiry{current?.expiry_required?" (required)":""}
          <input type="date" required={Boolean(current?.expiry_required)} value={validUntil}
            onChange={e=>{setValidUntil(e.target.value);resetRetry();}}/></label>
        <label>Source document<input type="file" required={!file}
          accept=".pdf,.docx,.png,.jpg,.jpeg,.txt"
          onChange={e=>{setFile(e.target.files?.[0]||null);resetRetry();}}/></label>
        {busy&&<div className="partner-progress"><progress max={100} value={progress}/><span>{progress}% uploaded</span></div>}
        <div className="partner-buttons"><button className="partner-primary" disabled={!current||!file||busy||(related!=="PROVIDER"&&!relatedId)||
             (current.acknowledgement_required&&!current.acknowledged_by_me)}>
          {busy?"Uploading…":"Submit for controlled review"}</button>
          {busy&&<button type="button" onClick={()=>{xhrRef.current?.abort();resumableAbort.current?.abort();}}>Cancel transfer</button>}
          {!busy&&file&&error&&<button type="button" onClick={resetRetry}>Start a new upload attempt</button>}
        </div>
      </form>
    </Section>}
    <Section title="Document submission history" description="Original evidence, previous revisions and Quality feedback remain available when a provider agreement ends.">
      <State pending={submissions.pending} error={submissions.error} retry={submissions.reload}/>
      {submissions.value?.items.map(s=><div key={s.id} className="partner-row">
        <div><strong>{s.filename}</strong>
          <small>{s.evidence_type} · {friendlyDate(s.created_at)} · {s.sha256.slice(0,12)}…</small>
          {s.form_revision_id&&<small>Form revision: {s.form_revision_id}</small>}
          {s.qms_evidence_id&&<small>QMS evidence reference: {s.qms_evidence_id} (verification separate)</small>}
          {s.dms_revision_id&&<small>Linked DMS revision: {s.dms_revision_id}</small>}
          {supersededIds.has(s.id)&&<small>Later submission recorded — retained as history</small>}
          {s.review_note&&<small>Review: {s.review_note}</small>}
        </div><div className="partner-buttons"><Status value={s.status}/>
          <button type="button" onClick={()=>void getOriginal(
            `documents/submissions/${encodeURIComponent(s.id)}/original`,s.filename)}>Download original</button>
          <button type="button" onClick={()=>void readOriginal(
            `documents/submissions/${encodeURIComponent(s.id)}/original`,s.filename)}>Read original</button>
        </div>
      </div>)}
      {submissions.value&&!submissions.value.items.length&&<p className="partner-empty">No document submissions have been recorded.</p>}
      <div className="partner-buttons">
        <button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous</button>
        <button disabled={!submissions.value?.has_more} onClick={()=>setOffset(offset+25)}>Next</button>
        <button type="button" onClick={refreshAll}>Refresh</button>
      </div>
    </Section>
    {preview&&<Section title={`Controlled reader — ${preview.name}`}
       description="Read-only original. Reading does not approve a document or authorize work.">
       <div className="partner-buttons"><button type="button" onClick={()=>{
         if(previewUrl.current)URL.revokeObjectURL(previewUrl.current);
         previewUrl.current="";setPreview(null);setPreviewText("");
       }}>Close reader</button></div>
       {preview.mime.includes("wordprocessingml")?
         <PublicationDocxLayoutViewer fileUrl="" fileBlob={preview.blob} title={preview.name}
           zoom="fit" onTextFallback={()=>setError("Word rendering unavailable. Download the original instead.")}/>:
         preview.mime.includes("application/pdf")?
           <iframe src={preview.url} title={preview.name} style={{width:"100%",minHeight:"70vh"}}/>:
         preview.mime.includes("image/")?
           <img src={preview.url} alt={preview.name} style={{maxWidth:"100%"}}/>:
         preview.mime.includes("text/plain")?<pre style={{whiteSpace:"pre-wrap"}}>{previewText}</pre>:
           <p>Use the original download to read this document.</p>}
    </Section>}
    <ActionNotice value={error} error/><ActionNotice value={notice}/>
  </div>;
}
