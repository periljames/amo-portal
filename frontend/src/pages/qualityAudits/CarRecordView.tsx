import { ResponseText } from "../../components/QMS/carRca/ResponseTextArea";
import InlineLoading from "../../components/shared/InlineLoading";
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowLeft, Download, FileText, Eye, ShieldCheck } from "lucide-react";

import { qmsListCarAttachments, qmsDownloadCarAttachmentBlob, qmsUploadCarAttachment, type CAROut, type CARAssignee } from "../../services/qms";
import CarEvidencePreview, { CarEvidenceThumbnail } from "./CarEvidencePreview";
import { sectionEvidence, decision, RESPONSE_SECTIONS, type ResponseSection } from "./carResponseEvidence";
import type { CARAttachmentOut } from "../../services/qms";
import type { CarRcaProjection } from "../../services/qmsCarRca";
import "./caseWorkspace.css";
import { carHasReview, carNextAction, caseDate } from "./carCaseModel";
import CarRcaInternalReview from "../../components/QMS/carRca/CarRcaInternalReview";
import CarFeedbackPanel from "../../components/QMS/carRca/CarFeedbackPanel";

type Props = { car: CAROut; amoCode: string; owner: string; assignees?: CARAssignee[]; canManage: boolean; canAttach: boolean; canReview: boolean;
  onEdit: () => void; onReview: () => void; onInvite: () => void; onExport: () => void };

export default function CarRecordView({car, amoCode, owner, assignees = [], canManage, canAttach, canReview, onEdit, onReview, onInvite, onExport}: Props) {
  const [preview,setPreview]=useState<CARAttachmentOut|null>(null);
  const [projection,setProjection]=useState<CarRcaProjection|null>(null);
  const previewHost=useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);

  const [file,setFile]=useState<File|null>(null);
  const [uploadSection,setUploadSection]=useState<ResponseSection|"">("");
  const [uploading,setUploading]=useState(false);
  const [fileVersion,setFileVersion]=useState(0);
  const files = useQuery({queryKey:["qms-car-attachments",amoCode,car.id], queryFn:()=>qmsListCarAttachments(car.id)});
  const base = `/maintenance/${encodeURIComponent(amoCode)}/quality`;
  const isReadOnly = ['CLOSED','CANCELLED','ESCALATED'].includes(car.status);
  const badge = (status?:string|null) => {const result=decision(status);return <span className="case-decision" data-decision={result.tone}>{result.label}</span>;};
  const show = (file:CARAttachmentOut) => {setPreview(file);if(window.matchMedia('(max-width:760px)').matches)requestAnimationFrame(()=>previewHost.current?.scrollIntoView({block:'nearest',behavior:'smooth'}));};
  const section = (key:ResponseSection,title:string,value?:string|null,note?:string|null,status?:string|null) => {
    const linked=sectionEvidence(files.data||[],projection,key,value);
    return <section className="case-response-block case-response-evidence" aria-label={title}>
      <div className="case-response-evidence__rail">{linked.map(file=><CarEvidenceThumbnail key={file.id} carId={car.id} file={file} section={title} onOpen={()=>show(file)}/>)}</div>
      <div className="case-response-evidence__body"><header><h3>{title}</h3>{status!==undefined?badge(status):null}</header>
        <div className={!value?'case-muted':'case-response-prose'}><ResponseText value={value||'Not submitted'}/></div>
        {note?<aside className="case-quality-decision" data-decision={decision(status).tone}><header><ShieldCheck size={15}/><strong>Quality review</strong></header><ResponseText value={note}/></aside>:null}
      </div>
    </section>;
  };
  const open = async(id:string,_filename:string) => {const file=files.data?.find(item=>item.id===id);if(file)show(file);};
  const upload = async()=>{
    if(!file) return;
    setUploading(true);setError(null);
    try {await qmsUploadCarAttachment(car.id,file,undefined,uploadSection||undefined);setFile(null);setFileVersion(v=>v+1);await files.refetch();}
    catch(cause){setError(cause instanceof Error?cause.message:"Evidence upload failed. Your selected file is retained for retry.");}
    finally {setUploading(false);}
  };
  return <article className="case-workspace" aria-label={`Corrective action ${car.car_number}`}>
    <Link className="case-back" to={`${base}/cars/register`}><ArrowLeft size={16}/>Corrective actions</Link>
    <header className="case-heading"><div><div className="case-meta"><span className="case-status" data-tone={car.status === "CLOSED" ? "success" : car.priority === "CRITICAL" ? "danger" : "info"}>{car.status.toLowerCase().replaceAll("_"," ")}</span><span>{car.priority.toLowerCase()} priority</span></div><h1>{car.car_number}</h1><p>{car.title}</p></div>
      <div className="case-actions">{canReview && carHasReview(car) ? <button className="case-primary" onClick={onReview}>Review response</button> : null}<Link className="case-button" to={`${base}/cars?control=${encodeURIComponent(car.id)}`}>{canManage ? "Action plan & closure" : "View action plan"}</Link><button onClick={onExport}><Download size={15}/>Evidence pack</button></div>
    </header>
    <dl className="case-facts"><div><dt>Responsible</dt><dd>{owner || "Unassigned"}<small>{car.responsible_department}</small></dd></div><div><dt>Due date</dt><dd>{caseDate(car.due_date)}</dd></div><div><dt>Next action</dt><dd>{carNextAction(car)}</dd></div><div><dt>Audit / finding</dt><dd>{car.finding_id ? <Link to={`${base}/findings/${encodeURIComponent(car.finding_id)}/overview`}>{car.finding_ref || "View finding"}</Link> : "Not linked"}<small>{car.audit_ref}</small></dd></div></dl>
    <div className={`case-columns${preview?" case-columns--evidence-open":""}`}><div>
      <section className="case-section"><h2>Non-conformance</h2><p>{car.finding_description || car.summary}</p>{car.finding_description && car.summary !== car.finding_description ? <p className="case-muted">{car.summary}</p> : null}</section>
      <section className="case-section case-response"><h2>Auditee response</h2>
        {car.containment_action || sectionEvidence(files.data||[],projection,"CONTAINMENT").length ? section("CONTAINMENT","Immediate action",car.containment_action) : null}
        {section("ROOT_CAUSE","Root cause",car.root_cause_text || car.root_cause,car.root_cause_review_note,car.root_cause_status||"PENDING")}
        {section("CORRECTIVE","Corrective Action (CAP)",car.capa_text || car.corrective_action,car.capa_review_note,car.capa_status||"PENDING")}
      </section>
      <CarRcaInternalReview amoCode={amoCode} carId={car.id} canReview={canReview && !isReadOnly} attachments={files.data || []} assignees={assignees} onOpenEvidence={open} openingId={opening} onProjectionChange={setProjection} />
    </div><aside>
      <div ref={previewHost}>{preview?<CarEvidencePreview key={preview.id} carId={car.id} file={preview} onClose={()=>setPreview(null)}/>:null}</div>
      <section className="case-section"><h2>Response & assurance</h2><dl className="case-key-values"><div><dt>Submitted</dt><dd>{car.submitted_at ? caseDate(car.submitted_at) : "Not submitted"}</dd></div><div><dt>Evidence verified</dt><dd>{car.evidence_verified_at ? caseDate(car.evidence_verified_at) : "Not verified"}</dd></div>{car.target_closure_date && car.target_closure_date.slice(0,10) !== car.due_date?.slice(0,10) ? <div><dt>Target closure</dt><dd>{caseDate(car.target_closure_date)}</dd></div> : null}{car.closed_at ? <div><dt>Closed</dt><dd>{caseDate(car.closed_at)}</dd></div> : null}</dl>{canManage ? <div className="case-actions">{!isReadOnly && <button onClick={onEdit}>Edit assignment & dates</button>}<button onClick={onInvite}>{isReadOnly ? "Copy history link" : "Copy response link"}</button></div> : null}</section>
      <section className="case-section"><h2><FileText size={17}/>Response evidence</h2>{error ? <p role="alert">{error}</p> : null}{files.isPending ? <p><InlineLoading label={"Loading files…"}/></p> : files.isError ? <p role="alert">Evidence could not be loaded. <button onClick={()=>void files.refetch()}>Retry</button></p> : !files.data?.length ? <p className="case-muted">No response files attached.</p> : <ul className="case-files">{files.data.map(file=><li key={file.id}><button disabled={opening===file.id} onClick={()=>void open(file.id,file.filename)}><Eye size={15}/>{file.filename}</button><small>{caseDate(file.uploaded_at)}</small></li>)}</ul>}
      {canAttach && !['CLOSED','CANCELLED','ESCALATED'].includes(car.status)?<details className="case-evidence-upload"><summary>Attach evidence</summary><label className="case-upload">Evidence for<select aria-label="Evidence response section" value={uploadSection} onChange={event=>setUploadSection(event.target.value as ResponseSection|"")}><option value="">General evidence</option>{RESPONSE_SECTIONS.map(section=><option key={section.value} value={section.value}>{section.label}</option>)}</select></label><label className="case-upload">File<input key={fileVersion} type="file" onChange={event=>setFile(event.target.files?.[0]||null)} disabled={uploading}/></label><button disabled={!file||uploading} onClick={()=>void upload()}>{uploading?'Attaching…':'Attach to CAR'}</button></details>:null}</section>
    <CarFeedbackPanel amoCode={amoCode} carId={car.id} canWrite={!isReadOnly && (canManage||canReview)} />
    </aside></div>
  </article>;
}
