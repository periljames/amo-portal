import { lazy, Suspense, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText, X } from "lucide-react";
import { qmsDownloadCarAttachmentBlob, type CARAttachmentOut } from "../../services/qms";
import { saveDownloadedFile } from "../../utils/downloads";
const Pdf=lazy(()=>import("./CarEvidencePdf"));
const Word=lazy(()=>import("../manuals/PublicationDocxLayoutViewer"));
function useEvidence(carId:string,file:CARAttachmentOut,enabled=true) {
 return useQuery({queryKey:['qms-car-evidence-blob',carId,file.id],queryFn:()=>qmsDownloadCarAttachmentBlob(carId,file.id),staleTime:300000,gcTime:300000,retry:false,enabled});
}
function useBlobUrl(blob?:Blob) {
 const [url,setUrl]=useState('');useEffect(()=>{if(!blob){setUrl('');return;}const objectUrl=URL.createObjectURL(blob);setUrl(objectUrl);return()=>URL.revokeObjectURL(objectUrl);},[blob]);return url;
}
function kind(file:CARAttachmentOut) {
 const mime=file.content_type||'';const ext=file.filename.toLowerCase().split('.').pop();
 if(mime==='application/pdf'||ext==='pdf')return 'pdf';
 if(mime.startsWith('image/')||['jpg','jpeg','png','webp','gif'].includes(ext||''))return 'image';
 if(ext==='docx')return 'word';if(mime.startsWith('video/'))return 'video';if(mime.startsWith('audio/'))return 'audio';
 if(mime.startsWith('text/')||['txt','csv','json'].includes(ext||''))return 'text';return 'other';
}
export function CarEvidenceThumbnail({carId,file,section,onOpen}:{carId:string;file:CARAttachmentOut;section:string;onOpen:()=>void}) {
 const type=kind(file);const query=useEvidence(carId,file,["pdf","image"].includes(type)&&(!file.size_bytes||file.size_bytes<=20*1024*1024));const url=useBlobUrl(query.data);
 return <button type="button" className="case-evidence-thumbnail" aria-label={`View ${file.filename} for ${section}`} onClick={onOpen}>
 <span className="case-evidence-thumbnail__page" aria-hidden="true">{query.data&&type==='pdf'?<Suspense fallback={<FileText size={26}/>}><Pdf blob={query.data} thumbnail/></Suspense>:url&&type==='image'?<img src={url} alt=""/>:<FileText size={26}/>}</span>
 <span>{file.filename}</span></button>;
}
export default function CarEvidencePreview({carId,file,onClose}:{carId:string;file:CARAttachmentOut;onClose:()=>void}) {
 const query=useEvidence(carId,file);const url=useBlobUrl(query.data);const type=kind(file);const [text,setText]=useState('');
 useEffect(()=>{let current=true;setText('');if(query.data&&type==='text')void query.data.slice(0,500000).text().then(value=>{if(current)setText(value);});return()=>{current=false;};},[query.data,type]);
 return <section className="case-evidence-viewer" aria-label="Evidence preview">
 <header><div><span>Evidence preview</span><h2>{file.filename}</h2></div><button type="button" aria-label="Close evidence preview" onClick={onClose}><X size={17}/></button></header>
 {query.isPending?<p role="status">Opening evidence…</p>:query.isError?<p role="alert">Evidence could not be opened. <button type="button" onClick={()=>void query.refetch()}>Retry preview</button></p>:query.data?<>
 <div className="case-evidence-viewer__document"><Suspense fallback={<p role="status">Opening document…</p>}>
 {type==='pdf'?<Pdf blob={query.data}/>:type==='image'?<img src={url} alt={file.filename}/>:type==='word'?<Word fileUrl="" fileBlob={query.data} title={file.filename} zoom="fit" onTextFallback={()=>setText('Word preview could not be rendered. Use the download option for this file.')}/>:type==='video'?<video src={url} controls/>:type==='audio'?<audio src={url} controls/>:type==='text'?<pre>{text}</pre>:<p>Inline preview is unavailable for this file format.</p>}
 {type==='word'&&text?<p role="alert">{text}</p>:null}
 </Suspense></div>
 <footer><button type="button" onClick={()=>saveDownloadedFile(query.data!,file.filename)}><Download size={14}/>Download a copy</button></footer>
 </>:null}</section>;
}
