import InlineLoading from "../../components/shared/InlineLoading";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Download, ExternalLink } from "lucide-react";
import { hasQmsRolePermission } from "../../app/routeGuards";
import type { CAROut, QMSFindingOut } from "../../services/qms";
import { downloadInternalAuditEvidence, listAuditEvidence, type AuditEvidenceArtifact } from "../../services/qmsAuditEvidence";
import { readRetainedAuditEvidence, retainDownloadedAuditEvidence } from "../../services/qmsOfflineAuditEvidence";
import { saveDownloadedFile } from "../../utils/downloads";
import { caseDate, carNextAction } from "./carCaseModel";
import "./caseWorkspace.css";

const findingIsObservation = (finding: QMSFindingOut) => finding.level === "LEVEL_4" || finding.finding_type === "OBSERVATION";

export default function FindingCaseView({finding, car, amoCode}: {finding:QMSFindingOut;car:CAROut|null;amoCode:string}) {
  const observation=findingIsObservation(finding);
  const [error,setError]=useState<string|null>(null);
  const [opening,setOpening]=useState<string|null>(null);
  const canReadAudit=hasQmsRolePermission("qms.audit.view");
  const files=useQuery({queryKey:["qms-finding-evidence",amoCode,finding.audit_id,finding.id],queryFn:({signal})=>listAuditEvidence(amoCode,finding.audit_id,null,finding.id,signal),enabled:canReadAudit});
  const base=`/maintenance/${encodeURIComponent(amoCode)}/quality`;
  const open=async(file:AuditEvidenceArtifact)=>{
    setError(null);setOpening(file.id);
    try {
      const cached=await readRetainedAuditEvidence(amoCode,finding.audit_id,file).catch(()=>null);
      if(!cached && !navigator.onLine) throw new Error("Open this evidence once online to save a copy on this device.");
      const blob=cached||await downloadInternalAuditEvidence(amoCode,finding.audit_id,file.id);
      if(!cached) await retainDownloadedAuditEvidence(amoCode,finding.audit_id,file,blob);
      saveDownloadedFile(blob,file.filename);
    } catch(cause){setError(cause instanceof Error?cause.message:"Evidence could not be opened.");}
    finally {setOpening(null);}
  };
  return <article className="case-workspace case-finding" aria-label="Finding case">
    <header className="case-heading"><div><div className="case-meta"><span className="case-status" data-tone={finding.closed_at?"success":finding.level==="LEVEL_1"?"danger":"info"}>{finding.closed_at?"Closed":observation?"Observation":"Open finding"}</span><span>{finding.level.replace("LEVEL_","Level ")}{!observation ? ` · ${finding.severity.toLowerCase()}` : ""}</span>{finding.safety_sensitive?<span className="case-status" data-tone="danger">Safety sensitive</span>:null}</div><h2>{finding.finding_ref || "Finding"}</h2></div><div className="case-actions">{car?<Link className="case-button" to={`${base}/cars?carId=${encodeURIComponent(car.id)}`}>Open {car.car_number}<ExternalLink size={14}/></Link>:!observation&&hasQmsRolePermission("qms.car.create")?<Link className="case-button" to={`${base}/cars/new?findingId=${encodeURIComponent(finding.id)}`}>Create corrective action</Link>:null}</div></header>
    <dl className="case-facts"><div><dt>Requirement</dt><dd>{finding.requirement_ref || "Not recorded"}</dd></div><div><dt>Responsible</dt><dd>{car?.responsible_personnel || "Unassigned"}</dd></div><div><dt>Target date</dt><dd>{caseDate(finding.target_close_date||car?.due_date)}</dd></div><div><dt>Next action</dt><dd>{finding.closed_at?"Closed":car?car.status==="CLOSED"?"Verify finding closure":carNextAction(car):observation?"Review observation":"Assign corrective action"}</dd></div></dl>
    <section className="case-section"><h3>Finding statement</h3><p>{finding.description}</p></section>
    <section className="case-section"><h3>Objective evidence</h3><p className={!finding.objective_evidence?"case-muted":undefined}>{finding.objective_evidence || "No objective-evidence statement recorded."}</p>{error?<p role="alert">{error}</p>:null}{canReadAudit?(files.isError?<p role="alert">Files could not be loaded. <button onClick={()=>void files.refetch()}>Retry</button></p>:files.isPending?<p><InlineLoading label={"Loading evidence…"}/></p>:<ul className="case-files">{files.data?.items.map(file=><li key={file.id}><button disabled={opening===file.id} onClick={()=>void open(file)}><Download size={15}/>{file.filename}</button><small>{file.description}</small></li>)}</ul>):null}</section>
    {car?<><section className="case-section"><h3>Root cause analysis</h3><p>{car.root_cause_text||car.root_cause||"Awaiting auditee submission."}</p>{car.root_cause_review_note?<p className="case-review-note"><span>Quality review</span>{car.root_cause_review_note}</p>:null}</section><section className="case-section"><h3>Corrective action</h3><p>{car.capa_text||car.corrective_action||"Awaiting action plan."}</p>{car.capa_review_note?<p className="case-review-note"><span>Quality review</span>{car.capa_review_note}</p>:null}</section></>:observation?<section className="case-section"><h3>Observation follow-up</h3><p className="case-muted">No nonconformity CAR is required for this observation.</p></section>:null}
    <section className="case-section"><h3>Record & acknowledgement</h3><dl className="case-key-values"><div><dt>Recorded</dt><dd>{caseDate(finding.created_at)}</dd></div><div><dt>Acknowledged</dt><dd>{finding.acknowledged_at?`${caseDate(finding.acknowledged_at)} · ${finding.acknowledged_by_name||finding.acknowledged_by_email||"Auditee"}`:"Not acknowledged"}</dd></div><div><dt>Verified</dt><dd>{finding.verified_at?caseDate(finding.verified_at):"Not verified"}</dd></div><div><dt>Closed</dt><dd>{finding.closed_at?caseDate(finding.closed_at):"Open"}</dd></div></dl></section>
    {canReadAudit?<Link className="case-button" to={`${base}/audits/${encodeURIComponent(finding.audit_id)}/live`}>Open source checklist<ExternalLink size={14}/></Link>:null}
  </article>;
}
