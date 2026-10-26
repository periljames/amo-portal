import { Plus, X } from "lucide-react";

export default function TextItemList({ label, value, onChange, required = false, disabled = false }: { label: string; value: string[]; onChange: (value: string[]) => void; required?: boolean; disabled?: boolean }) {
  const rows = value.length ? value : [""];
  return <fieldset className="qms-email-list"><legend>{label}</legend><p>Add one item per field.</p>
    {rows.map((item, index) => <div className="qms-email-list__row" key={index}><label><span className="sr-only">{label} {index + 1}</span><input value={item} required={required || rows.length > 1} maxLength={1000} disabled={disabled} onChange={event => onChange(rows.map((other, position) => position === index ? event.target.value : other))} /></label>{rows.length > 1 && <button type="button" disabled={disabled} aria-label={`Remove ${label.toLowerCase()} ${index + 1}`} onClick={() => onChange(rows.filter((_, position) => position !== index))}><X size={16} /></button>}</div>)}
    <button type="button" className="qms-email-list__add" disabled={disabled || rows.some(item => !item.trim()) || rows.length >= 100} onClick={() => onChange([...rows, ""])}><Plus size={16} /> Add item</button>
  </fieldset>;
}
