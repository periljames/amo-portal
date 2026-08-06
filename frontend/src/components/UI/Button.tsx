import React from "react";
import { clsx } from "clsx";

import "./Button.css";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  loadingLabel?: React.ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  iconOnly?: boolean;
}

const Button: React.FC<ButtonProps> = ({
  children,
  loading = false,
  loadingLabel = "Please wait",
  variant = "primary",
  size = "md",
  block = false,
  iconOnly = false,
  className,
  type,
  disabled,
  ...rest
}) => {
  return (
    <button
      {...rest}
      type={type ?? "button"}
      className={clsx(
        "btn",
        `btn--${variant}`,
        `btn--${size}`,
        block && "btn--block",
        iconOnly && "btn--icon-only",
        loading && "btn--loading",
        className,
      )}
      disabled={loading || disabled}
      aria-busy={loading || undefined}
      data-loading={loading || undefined}
    >
      <span className="btn__content">
        {loading ? <span className="btn__spinner" aria-hidden="true" /> : null}
        <span className="btn__label">{loading ? loadingLabel : children}</span>
      </span>
    </button>
  );
};

export default Button;
