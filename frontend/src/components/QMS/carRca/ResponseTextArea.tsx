import { useRef, useState, type TextareaHTMLAttributes } from "react";
import ReactMarkdown from "react-markdown";
import "./response-text-area.css";

type Props = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "onChange"> & {
 value: string; onValueChange: (value: string) => void;
};
export function ResponseText({value}:{value:string}) {
 return <ReactMarkdown skipHtml components={{img:()=>null,a:({children,href})=><a href={href} target="_blank" rel="noopener noreferrer">{children}</a>}}>{value}</ReactMarkdown>;
}
export default function ResponseTextArea({value,onValueChange,disabled,maxLength=8000,onKeyDown,...props}:Props) {
 const input=useRef<HTMLTextAreaElement>(null);
 const [preview,setPreview]=useState(false);
 const [expanded,setExpanded]=useState(false);
 const format=(before:string,after="",placeholder="text")=>{
  const field=input.current;if(!field||disabled)return;
  const start=field.selectionStart,end=field.selectionEnd;
  const selected=value.slice(start,end)||placeholder;
  const next=value.slice(0,start)+before+selected+after+value.slice(end);
  if(next.length>maxLength)return;
  onValueChange(next);
  requestAnimationFrame(()=>{field.focus();field.setSelectionRange(start+before.length,start+before.length+selected.length);});
 };
 return <div className={`response-text-area${expanded?" is-expanded":""}`}>
  <div className="response-text-area__tools" role="toolbar" aria-label="Text formatting" onMouseDown={event=>event.preventDefault()}>
   {!preview&&<><button type="button" disabled={disabled} aria-label="Bold text" title="Bold (Ctrl+B)" onClick={()=>format('**','**')}><b>B</b></button>
   <button type="button" disabled={disabled} aria-label="Italic text" title="Italic (Ctrl+I)" onClick={()=>format('*','*')}><i>I</i></button>
   <button type="button" disabled={disabled} onClick={()=>format('\n## ','','Heading')}>Heading</button>
   <button type="button" disabled={disabled} onClick={()=>format('\n> ','','Quote')}>Quote</button>
   <button type="button" disabled={disabled} onClick={()=>format('\n- ','','Item')}>Bullets</button>
   <button type="button" disabled={disabled} onClick={()=>format('\n1. ','','Item')}>Numbers</button>
   <button type="button" disabled={disabled} onClick={()=>format('[','](https://example.com)','Link text')}>Link</button></>}
   <button type="button" aria-label={preview?"Edit text":"Preview"} aria-pressed={preview} onClick={()=>setPreview(current=>!current)}>{preview?'Edit text':'Preview'}</button>
   <button type="button" aria-label={expanded?"Reduce editor":"Expand editor"} aria-pressed={expanded} onClick={()=>setExpanded(current=>!current)}>{expanded?'Reduce':'Expand'}</button>
  </div>
  <textarea {...props} ref={input} value={value} hidden={preview} disabled={disabled} maxLength={maxLength} onChange={event=>onValueChange(event.target.value)} onKeyDown={event=>{
   if((event.ctrlKey||event.metaKey)&&['b','i'].includes(event.key.toLowerCase())) {event.preventDefault();format(event.key.toLowerCase()==='b'?'**':'*',event.key.toLowerCase()==='b'?'**':'*');return;}
   if(event.key==='Enter'&&!event.shiftKey) {
    const field=event.currentTarget,start=field.selectionStart,end=field.selectionEnd;
    const line=value.slice(0,start).split('\n').pop()||'';
    const match=line.match(/^(\s*)([-*•]|\d+\.)\s+(.*)$/);
    if(match&&match[3].trim()) {
     event.preventDefault();const marker=/^\d/.test(match[2])?`${parseInt(match[2])+1}.`:match[2];
     const inserted=`\n${match[1]}${marker} `;const next=value.slice(0,start)+inserted+value.slice(end);
     if(next.length<=maxLength) {onValueChange(next);requestAnimationFrame(()=>field.setSelectionRange(start+inserted.length,start+inserted.length));}
     return;
    }
   }
   onKeyDown?.(event);
  }}/>
  {preview&&<div className="response-text-area__preview" role="region" aria-label="Formatted text preview"><ResponseText value={value||"Nothing to preview yet."}/></div>}
  {value.length>maxLength-100&&<small>{maxLength-value.length} characters remaining</small>}
 </div>;
}
