import React from "react";
import { Plus, X } from "lucide-react";
import { validEmailList } from "./emailAddresses";

export default function EmailAddressList({ value, onChange, label = "Email addresses", disabled = false }: {
  value: string[]; onChange: (value: string[]) => void; label?: string; disabled?: boolean;
}) {
  const rows = value.length ? value : [""];
  return <fieldset className="qms-email-list"><legend>{label}</legend>
    <p>Add one address per field. Use + to add another address.</p>
    {rows.map((email, index) => {
      const duplicate = Boolean(email.trim()) && rows.some((other, position) => position !== index && other.trim().toLowerCase() === email.trim().toLowerCase());
      return <div className="qms-email-list__row" key={index}>
        <label><span className="sr-only">{label} {index + 1}</span><input aria-label={`${label} ${index + 1}`} type="email" required maxLength={254} autoComplete="email" autoCapitalize="none" spellCheck={false}
          pattern={"[^\\s@,;]+@[^\\s@,;]+\\.[^\\s@,;]+"} value={email} disabled={disabled}
          ref={node => node?.setCustomValidity(duplicate ? "This email address has already been added." : "")}
          onChange={event => onChange(rows.map((item, position) => position === index ? event.target.value : item))} placeholder="name@organization.com" /></label>
        {rows.length > 1 && <button type="button" disabled={disabled} aria-label={`Remove email ${index + 1}`} onClick={() => onChange(rows.filter((_, position) => position !== index))}><X size={16} /></button>}
      </div>;
    })}
    <button type="button" className="qms-email-list__add" disabled={disabled || !validEmailList(rows) || rows.length >= 20} onClick={() => onChange([...rows, ""])}><Plus size={16} /> Add email</button>
  </fieldset>;
}
