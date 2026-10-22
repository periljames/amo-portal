import { useState } from "react";
import { ArrowRight, ChevronFirst, ChevronLast, ChevronLeft, ChevronRight } from "lucide-react";
import "./pagination.css";
import { pageNumbers } from "./paginationModel";
export default function Pagination({ page, pageSize, total, visibleCount, hasNext = false, busy = false, onPageChange, onPageSizeChange, pageSizes = [25,50,100], label = "Records" }: {
  page: number; pageSize: number; total?: number; visibleCount: number; hasNext?: boolean; busy?: boolean;
  onPageChange: (page:number)=>void; onPageSizeChange?: (size:number)=>void; pageSizes?: readonly number[]; label?: string;
}) {
  const pages = total == null ? undefined : Math.max(1,Math.ceil(total/pageSize));
  const [entry, setEntry] = useState({ page, value: String(page) });
  if (entry.page !== page) setEntry({ page, value: String(page) });
  const draft = entry.page === page ? entry.value : String(page);
  const setDraft = (value: string) => setEntry({ page, value });
  const change = (value:number) => { if(Number.isSafeInteger(value) && value>=1 && (pages==null || value<=pages) && value!==page)onPageChange(value); };
  return <nav className="record-pagination" aria-label={`${label} pagination`} aria-busy={busy}>
    <span className="record-pagination__summary">{visibleCount ? `${((page-1)*pageSize+1).toLocaleString()}–${((page-1)*pageSize+visibleCount).toLocaleString()}` : "0"}{total!=null ? ` of ${total.toLocaleString()}` : " records"}</span>
    {onPageSizeChange ? <label>Rows <select aria-label={`${label} rows per page`} value={pageSize} disabled={false} onChange={event=>onPageSizeChange(Number(event.target.value))}>{pageSizes.map(size=><option key={size} value={size}>{size}</option>)}</select></label> : null}
    <div className="record-pagination__pages">
      <button type="button" title="First page" aria-label="First page" disabled={page<=1} onClick={()=>change(1)}><ChevronFirst size={16}/></button>
      <button type="button" title="Previous page" aria-label="Previous page" disabled={page<=1} onClick={()=>change(page-1)}><ChevronLeft size={16}/></button>
      {pageNumbers(page,pages,hasNext).map(item=>typeof item==='number' ? <button type="button" key={item} disabled={false} aria-label={`Page ${item}`} aria-current={item===page ? "page" : undefined} onClick={()=>change(item)}>{item}</button> : <span key={item} aria-hidden="true">…</span>)}
      <button type="button" title="Next page" aria-label="Next page" disabled={(pages!=null ? page>=pages : !hasNext)} onClick={()=>change(page+1)}><ChevronRight size={16}/></button>
      {pages!=null ? <button type="button" title="Last page" aria-label="Last page" disabled={page>=pages} onClick={()=>change(pages)}><ChevronLast size={16}/></button> : null}
    </div>
    <span className="record-pagination__position">Page {page}{pages!=null ? ` of ${pages.toLocaleString()}` : ""}</span>
    <form onSubmit={event=>{event.preventDefault();change(Number(draft));}}><label>Go to page <input aria-label={`${label} page number`} type="number" min={1} max={pages} step={1} value={draft} disabled={false} onChange={event=>setDraft(event.target.value)} /></label><button type="submit" disabled={false} title="Go to page" aria-label="Go to page"><ArrowRight size={16}/></button></form>
  </nav>;
}
