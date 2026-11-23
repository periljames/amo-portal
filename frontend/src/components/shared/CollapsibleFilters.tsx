import { useEffect, useId, useState, type ReactNode } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import './collapsibleFilters.css';
export default function CollapsibleFilters({children,active=0,label='Filters'}:{children:ReactNode;active?:number;label?:string}) {
 const id=useId();const [open,setOpen]=useState(()=>typeof window==='undefined'||!window.matchMedia('(max-width: 700px)').matches);
 useEffect(()=>{const media=window.matchMedia('(max-width: 700px)');const update=()=>setOpen(!media.matches);media.addEventListener('change',update);return()=>media.removeEventListener('change',update);},[]);
 return <div className="qms-collapsible-filters"><button type="button" className="qms-collapsible-filters__toggle" aria-label={label} aria-expanded={open} aria-controls={id} onClick={()=>setOpen(!open)}><SlidersHorizontal size={18}/><span>{label}</span>{active>0&&<b>{active}</b>}</button><div id={id} className="qms-collapsible-filters__fields" hidden={!open}>{children}</div></div>;
}
