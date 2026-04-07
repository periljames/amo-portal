import React from "react";
import { clsx } from "clsx";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  iconOnly?: boolean;
}

const Button: React.FC<ButtonProps> = ({
  children,
  loading = false,
  variant = "primary",
  size = "md",
  block = false,
  iconOnly = false,
  className,
  type,
  ...rest
}) => {
  return (
    <button
      type={type ?? "button"}
      className={clsx(
        "btn",
        `btn--${variant}`,
        `btn--${size}`,
        block && "btn--block",
        iconOnly && "btn--icon-only",
        loading && "btn--loading",
        className
      )}
      disabled={loading || rest.disabled}
      aria-busy={loading || undefined}
      {...rest}
    >
      <span className="btn__content">{loading ? "Please wait..." : children}</span>
    </button>
  );
};

export default Button;
