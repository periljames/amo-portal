import InlineLoading from "../../components/shared/InlineLoading";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowLeft, Download, FileText } from "lucide-react";
import AuditHistoryPanel from "../../components/QMS/AuditHistoryPanel";
import { qmsListCarAttachments, qmsDownloadCarAttachmentBlob, qmsUploadCarAttachment, type CAROut } from "../../services/qms";
import { saveDownloadedFile } from "../../utils/downloads";
import "./caseWorkspace.css";
import { carHasReview, carNextAction, caseDate } from "./carCaseModel";
import CarRcaInternalReview from "../../components/QMS/carRca/CarRcaInternalReview";

type Props = { car: CAROut; amoCode: string; owner: string; canManage: boolean; canAttach: boolean; canReview: boolean;
  onEdit: () => void; onReview: () => void; onInvite: () => void; onExport: () => void };

export default function CarRecordView({car, amoCode, owner, canManage, canAttach, canReview, onEdit, onReview, onInvite, onExport}: Props) {
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [historyOpen,setHistoryOpen] = useState(false);
  const [file,setFile]=useState<File|null>(null);
  const [uploading,setUploading]=useState(false);
  const [fileVersion,setFileVersion]=useState(0);
  const files = useQuery({queryKey:["qms-car-attachments",amoCode,car.id], queryFn:()=>qmsListCarAttachments(car.id)});
  const base = `/maintenance/${encodeURIComponent(amoCode)}/quality`;
  const section = (title: string, value?: string | null, note?: string | null) => <section className="case-section"><h3>{title}</h3><p className={!value ? "case-muted" : undefined}>{value || "Not submitted"}</p>{note ? <p className="case-review-note"><span>Quality review</span>{note}</p> : null}</section>;
  const open = async (id: string, filename: string) => {
    setOpening(id); setError(null);
    try { saveDownloadedFile(await qmsDownloadCarAttachmentBlob(car.id,id),filename); }
    catch(cause) { setError(cause instanceof Error ? cause.message : "File could not be opened."); }
    finally {setOpening(null);}
  };
  const upload = async()=>{
    if(!file) return;
    setUploading(true);setError(null);
    try {await qmsUploadCarAttachment(car.id,file);setFile(null);setFileVersion(v=>v+1);await files.refetch();}
    catch(cause){setError(cause instanceof Error?cause.message:"Evidence upload failed. Your selected file is retained for retry.");}
    finally {setUploading(false);}
  };
  return <article className="case-workspace" aria-label={`Corrective action ${car.car_number}`}>
    <Link className="case-back" to={`${base}/cars/register`}><ArrowLeft size={16}/>Corrective actions</Link>
    <header className="case-heading"><div><div className="case-meta"><span className="case-status" data-tone={car.status === "CLOSED" ? "success" : car.priority === "CRITICAL" ? "danger" : "info"}>{car.status.toLowerCase().replaceAll("_"," ")}</span><span>{car.priority.toLowerCase()} priority</span></div><h1>{car.car_number}</h1><p>{car.title}</p></div>
      <div className="case-actions">{canReview && carHasReview(car) ? <button className="case-primary" onClick={onReview}>Review response</button> : null}<Link className="case-button" to={`${base}/cars?control=${encodeURIComponent(car.id)}`}>{canManage ? "Action plan & closure" : "View action plan"}</Link><button onClick={onExport}><Download size={15}/>Evidence pack</button></div>
    </header>
    <dl className="case-facts"><div><dt>Responsible</dt><dd>{owner || "Unassigned"}<small>{car.responsible_department}</small></dd></div><div><dt>Due date</dt><dd>{caseDate(car.due_date)}</dd></div><div><dt>Next action</dt><dd>{carNextAction(car)}</dd></div><div><dt>Audit / finding</dt><dd>{car.finding_id ? <Link to={`${base}/findings/${encodeURIComponent(car.finding_id)}/overview`}>{car.finding_ref || "View finding"}</Link> : "Not linked"}<small>{car.audit_ref}</small></dd></div></dl>
    <div className="case-columns"><div>
      <section className="case-section"><h2>Finding & requirement</h2><p>{car.finding_description || car.summary}</p>{car.finding_description && car.summary !== car.finding_description ? <details><summary>Original CAR statement</summary><p>{car.summary}</p></details> : null}</section>
      {section("Immediate correction / containment",car.containment_action)}
      {section("Root cause analysis",car.root_cause_text || car.root_cause,car.root_cause_review_note)}
      <CarRcaInternalReview amoCode={amoCode} carId={car.id} canReview={canReview} />
      {section("Corrective action plan",car.capa_text || car.corrective_action,car.capa_review_note)}
      {section("Preventive action",car.preventive_action)}
    </div><aside>
      <section className="case-section"><h2>Response & assurance</h2><dl className="case-key-values"><div><dt>Root cause</dt><dd>{car.root_cause_status?.toLowerCase().replaceAll("_"," ") || "Pending"}</dd></div><div><dt>Action plan</dt><dd>{car.capa_status?.toLowerCase().replaceAll("_"," ") || "Pending"}</dd></div><div><dt>Submitted</dt><dd>{car.submitted_at ? caseDate(car.submitted_at) : "Not submitted"}</dd></div><div><dt>Evidence verified</dt><dd>{car.evidence_verified_at ? caseDate(car.evidence_verified_at) : "Not verified"}</dd></div><div><dt>Target closure</dt><dd>{caseDate(car.target_closure_date)}</dd></div><div><dt>Closed</dt><dd>{car.closed_at ? caseDate(car.closed_at) : "Open"}</dd></div></dl>{canManage ? <div className="case-actions"><button onClick={onEdit}>Edit assignment & dates</button><button onClick={onInvite}>Copy response link</button></div> : null}</section>
      <section className="case-section"><h2><FileText size={17}/>Response evidence</h2>{error ? <p role="alert">{error}</p> : null}{files.isPending ? <p><InlineLoading label={"Loading files…"}/></p> : files.isError ? <p role="alert">Evidence could not be loaded. <button onClick={()=>void files.refetch()}>Retry</button></p> : !files.data?.length ? <p className="case-muted">No response files attached.</p> : <ul className="case-files">{files.data.map(file=><li key={file.id}><button disabled={opening===file.id} onClick={()=>void open(file.id,file.filename)}><Download size={15}/>{file.filename}</button><small>{caseDate(file.uploaded_at)}</small></li>)}</ul>}</section>
      {canAttach && !['CLOSED','CANCELLED','ESCALATED'].includes(car.status)?<section className="case-section"><h3>Attach evidence</h3><label className="case-upload">File<input key={fileVersion} type="file" onChange={event=>setFile(event.target.files?.[0]||null)} disabled={uploading}/></label><button disabled={!file||uploading} onClick={()=>void upload()}>{uploading?'Attaching…':'Attach to CAR'}</button></section>:null}
    </aside></div>
    <details className="case-section" onToggle={event=>setHistoryOpen(event.currentTarget.open)}><summary>Activity & decision history</summary>{historyOpen?<AuditHistoryPanel title="CAR history" entityType="qms_car" entityId={car.id} limit={12}/>:null}</details>
  </article>;
}
