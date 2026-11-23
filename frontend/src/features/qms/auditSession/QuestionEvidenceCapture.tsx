import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getCachedUser } from "../../../services/auth";
import PhoneEvidenceHandoff from "./PhoneEvidenceHandoff";
import { Camera, Paperclip, Upload, Smartphone } from "lucide-react";
import { enqueueOfflineAuditEvidence, listOfflineAuditEvidence, onOfflineAuditEvidenceChanged, discardOfflineAuditEvidence, retryOfflineAuditEvidence } from "../../../services/qmsOfflineAuditEvidence";
import { createEvidenceMutationId, listAuditEvidence, removeInternalAuditEvidence } from "../../../services/qmsAuditEvidence";
import { requestPortalOfflineSync } from "../../../services/portalOfflineSync";
import type { ChecklistExecutionGovernanceRow } from "../../../services/qmsChecklistExecutionGovernance";

export default function QuestionEvidenceCapture({ amoCode, auditId, item, disabled, pending = 0 }: {
  amoCode: string; auditId: string; item: ChecklistExecutionGovernanceRow; disabled: boolean; pending?: number;
}) {
  const queryClient=useQueryClient();
  const [filesOpen,setFilesOpen]=useState(false);
  const [fileAction,setFileAction]=useState('');
  const localFiles=useQuery({queryKey:['qms','question-evidence-pending',amoCode,auditId,item.checklist_item_id],queryFn:()=>listOfflineAuditEvidence(amoCode,auditId,item.checklist_item_id),enabled:filesOpen});
  const remoteFiles=useQuery({queryKey:['qms','question-evidence-saved',amoCode,auditId,item.checklist_item_id],queryFn:()=>listAuditEvidence(amoCode,auditId,item.checklist_item_id),enabled:filesOpen && navigator.onLine!==false,staleTime:1000});
  useEffect(()=>{if(!filesOpen)return;return onOfflineAuditEvidenceChanged(()=>{void localFiles.refetch();void remoteFiles.refetch();});},[filesOpen,amoCode,auditId,item.checklist_item_id]);
  const changeFile=async(id:string,action:'remove-local'|'retry'|'remove-saved')=>{
    setFileAction(id);setError('');
    try{if(action==='remove-local')await discardOfflineAuditEvidence(id,amoCode,auditId);
      else if(action==='retry'){await retryOfflineAuditEvidence(id,amoCode,auditId);requestPortalOfflineSync(true);}
      else await removeInternalAuditEvidence(amoCode,auditId,id,item.entity_version);
      await queryClient.invalidateQueries({predicate:q=>q.queryKey.includes(auditId)});
      setSaved(action==='retry'?'Upload queued for retry':'Attachment removed');
    }catch(cause){setError(cause instanceof Error?cause.message:'Attachment could not be changed. Try again.');await remoteFiles.refetch();}
    finally{setFileAction('');}
  };
  const upload = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);
  const [phoneOpen, setPhoneOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [cameraOpen, setCameraOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const request = useRef(0);
  const saving = useRef(false);
  const stopCamera = () => {
    request.current++;
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    setCameraOpen(false); setReady(false);
  };
  useEffect(() => () => { request.current++; stream.current?.getTracks().forEach(track => track.stop()); }, []);
  useEffect(() => {
    if (cameraOpen && dialog.current && !dialog.current.open) dialog.current.showModal();
  }, [cameraOpen]);
  const openCamera = async () => {
    setError("");
    if (/Android|iPhone|iPad|iPod/i.test(navigator.userAgent) || !navigator.mediaDevices?.getUserMedia) {
      camera.current?.click(); return;
    }
    setCameraOpen(true); setReady(false);
    const id = ++request.current;
    try {
      const acquired = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      if (id !== request.current) { acquired.getTracks().forEach(track => track.stop()); return; }
      stream.current = acquired;
      if (video.current) { video.current.srcObject = acquired; await video.current.play(); }
    } catch (cause) {
      if (id === request.current) setError(cause instanceof Error ? cause.message : "Camera unavailable. Upload a photo instead.");
    }
  };
  const saveFiles = async (files: File[]) => {
    if (!files.length || saving.current || disabled) return;
    saving.current = true;
    setBusy(true); setError(""); setSaved("");
    try {
      for (const file of files) await enqueueOfflineAuditEvidence({
        amoCode, auditId, checklistItemId: item.checklist_item_id, findingId: item.finding_id,
        file, clientMutationId: createEvidenceMutationId(), baseVersion: item.entity_version,
      });
      setFilesOpen(true);
      setSaved(`${files.length === 1 ? files[0].name : `${files.length} files`} saved on this device`);
      requestPortalOfflineSync(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Evidence could not be saved on this device. Keep the original and retry.");
    } finally { saving.current = false; setBusy(false); }
  };
  const capture = async (input: HTMLInputElement) => {
    const files = [...(input.files || [])]; input.value = ""; await saveFiles(files);
  };
  const photograph = async () => {
    if (!ready || !video.current?.videoWidth || saving.current) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.current.videoWidth; canvas.height = video.current.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) { setError("Camera image could not be created. Try uploading a photo."); return; }
    context.drawImage(video.current, 0, 0);
    const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", 0.92));
    if (!blob) { setError("Photo could not be captured. Try again."); return; }
    stopCamera();
    await saveFiles([new File([blob], `audit-evidence-${Date.now()}.jpg`, { type: "image/jpeg" })]);
  };
  return <div className="audit-question-attachments">
    <details open={filesOpen} onToggle={event=>setFilesOpen(event.currentTarget.open)}><summary aria-label={`Attach evidence for ${item.checklist_ref || "question"}`} aria-disabled={disabled || busy}>
      <Paperclip size={16} aria-hidden /><span>{busy ? "Saving…" : "Attach"}</span>{pending ? <small>{pending} pending</small> : null}
    </summary><div className="audit-question-attachments__choices">
      <button type="button" disabled={disabled || busy} onClick={() => upload.current?.click()}><Upload size={16} />Upload files</button>
      <button type="button" disabled={disabled || busy} onClick={() => void openCamera()}><Camera size={16} />Take photo</button>
      <button type="button" disabled={disabled || busy} onClick={() => setPhoneOpen(true)}><Smartphone size={16} />Use phone camera</button>
    </div>
    {(localFiles.isError || remoteFiles.isError) && <button type="button" onClick={()=>{void localFiles.refetch();void remoteFiles.refetch();}}>Retry attachment list</button>}
    <ul className="audit-question-files" aria-label="Question attachments">
      {(localFiles.data||[]).map(file=><li key={file.id}><span><strong>{file.filename}</strong><small>{file.state==='UPLOAD_FAILED'?'Upload failed':file.state==='CONFLICT'?'Needs retry':file.state==='UPLOADING'?'Uploading…':'Saved on device'}</small></span><button type="button" disabled={disabled||Boolean(fileAction)||file.state==='UPLOADING'} onClick={()=>void changeFile(file.id,'retry')} aria-label={`Retry ${file.filename}`}>Retry</button><button type="button" disabled={disabled||Boolean(fileAction)||file.state==='UPLOADING'} onClick={()=>void changeFile(file.id,'remove-local')} aria-label={`Remove ${file.filename}`}>Remove</button></li>)}
      {(remoteFiles.data?.items||[]).map(file=><li key={file.id}><span><strong>{file.filename}</strong><small>Uploaded</small></span>{file.uploaded_by_user_id===getCachedUser()?.id && <button type="button" disabled={disabled||Boolean(fileAction)} onClick={()=>void changeFile(file.id,'remove-saved')} aria-label={`Remove ${file.filename}`}>Remove</button>}</li>)}
    </ul></details>
    <input ref={upload} type="file" multiple hidden aria-label="Upload question evidence" onChange={(event) => void capture(event.currentTarget)} />
    <input ref={camera} type="file" accept="image/*" capture="environment" hidden aria-label="Photograph question evidence" onChange={(event) => void capture(event.currentTarget)} />
    {phoneOpen ? <PhoneEvidenceHandoff amoCode={amoCode} auditId={auditId} itemId={item.checklist_item_id} question={item.prompt} onClose={() => setPhoneOpen(false)} /> : null}
    {saved ? <small role="status">{saved}</small> : null}
    {error && !cameraOpen ? <small role="alert">{error}</small> : null}
    {cameraOpen ? <dialog ref={dialog} className="audit-evidence-camera" aria-label="Camera capture" onCancel={stopCamera}>
      <header><h2>Photograph evidence</h2><button type="button" aria-label="Close camera" onClick={stopCamera}>Close</button></header>
      <video ref={video} autoPlay playsInline muted onLoadedData={() => setReady(true)} />
      {error ? <p role="alert">{error}</p> : !ready ? <p>Waiting for camera preview…</p> : null}
      <footer><button type="button" disabled={!ready || busy} onClick={() => void photograph()}>Capture photo</button>
      <button type="button" onClick={() => { stopCamera(); upload.current?.click(); }}>Upload files instead</button></footer>
    </dialog> : null}
  </div>;
}
