import React from "react";
import { clsx } from "clsx";

interface TextFieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

const TextField: React.FC<TextFieldProps> = ({ label, error, className, ...rest }) => {
  const id = rest.id ?? rest.name ?? `input-${label.replace(/\s+/g, "-").toLowerCase()}`;

  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className={clsx("field__input", error && "field__input--error", className)}
        {...rest}
      />
      {error && <p className="field__error">{error}</p>}
    </div>
  );
};

export default TextField;
