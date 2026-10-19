import { useId, useState, type ReactNode } from "react";
import { MoreHorizontal } from "lucide-react";

export default function CarActionsMenu({label, children}: {label: string; children: ReactNode}) {
  const id = useId();
  const [position, setPosition] = useState({top:0,left:0});
  const [open,setOpen] = useState(false);
  return <><button type="button" aria-label={`Actions for ${label}`} aria-expanded={open} popoverTarget={id} onClick={event=>{
    const rect=event.currentTarget.getBoundingClientRect();
    setPosition({top:Math.max(8,Math.min(rect.bottom+6,window.innerHeight-300)),left:Math.max(8,Math.min(rect.right-230,window.innerWidth-238))});
  }}><MoreHorizontal size={16}/></button><div id={id} popover="auto" className="case-row-popover" aria-label={`${label} actions`} style={position} onToggle={event=>setOpen(event.currentTarget.matches(':popover-open'))} onClick={event=>{
    if((event.target as HTMLElement).closest('button')) event.currentTarget.hidePopover();
  }}>{children}</div></>;
}
