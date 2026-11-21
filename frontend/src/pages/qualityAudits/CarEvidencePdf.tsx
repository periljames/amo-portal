import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs",import.meta.url).toString();
const options={isEvalSupported:false};
export default function CarEvidencePdf({blob,thumbnail=false}:{blob:Blob;thumbnail?:boolean}) {
 const host=useRef<HTMLDivElement>(null);const [width,setWidth]=useState(300);const [count,setCount]=useState(1);const [page,setPage]=useState(1);
 useEffect(()=>{if(!host.current)return;const resize=()=>setWidth(Math.max(100,host.current!.clientWidth-4));resize();const observer=new ResizeObserver(resize);observer.observe(host.current);return()=>observer.disconnect();},[]);
 return <div ref={host} className="case-evidence-pdf">
 {!thumbnail&&<nav aria-label="Evidence document pages"><button type="button" disabled={page<=1} onClick={()=>setPage(value=>value-1)}>Previous</button><span>Page {page} of {count}</span><button type="button" disabled={page>=count} onClick={()=>setPage(value=>value+1)}>Next</button></nav>}
 <Document file={blob} options={options} loading={<span>Opening PDF…</span>} error={<span>PDF preview unavailable. You can download this file instead.</span>} onLoadSuccess={({numPages})=>setCount(numPages)}>
 <Page pageNumber={thumbnail?1:page} width={thumbnail?80:width} renderAnnotationLayer={false} renderTextLayer={false}/>
 </Document></div>;
}
