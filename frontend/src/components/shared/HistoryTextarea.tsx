import React from "react";

type Props = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  listId: string;
  onRemember?: (value: string) => void;
  rows?: number;
  placeholder?: string;
  required?: boolean;
};

/**
 * Textarea with a compact “Recent” picker for previously used lines.
 */
export function HistoryTextarea({
  label,
  value,
  onChange,
  options,
  listId,
  onRemember,
  rows = 3,
  placeholder,
  required,
}: Props) {
  return (
    <label className="is-wide qms-field-with-history">
      <span className="qms-field-with-history__label">
        <span>{label}</span>
        {options.length ? (
          <select
            aria-label={`Recent ${label}`}
            className="qms-field-with-history__recent"
            defaultValue=""
            onChange={(event) => {
              const picked = event.target.value;
              if (!picked) return;
              onChange(value.trim() ? `${value.trimEnd()}\n${picked}` : picked);
              event.currentTarget.value = "";
            }}
          >
            <option value="">Recent…</option>
            {options.map((option) => (
              <option key={option} value={option}>
                {option.length > 72 ? `${option.slice(0, 69)}…` : option}
              </option>
            ))}
          </select>
        ) : null}
      </span>
      <textarea
        rows={rows}
        required={required}
        list={listId}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        onBlur={() => onRemember?.(value)}
      />
      <datalist id={listId}>
        {options.map((option) => (
          <option key={option} value={option} />
        ))}
      </datalist>
    </label>
  );
}
