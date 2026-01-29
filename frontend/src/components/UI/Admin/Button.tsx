import React from "react";
import { clsx } from "clsx";

export type AdminButtonVariant = "primary" | "secondary" | "ghost";
export type AdminButtonSize = "sm" | "md";

export interface AdminButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: AdminButtonVariant;
  size?: AdminButtonSize;
  loading?: boolean;
}

const Button: React.FC<AdminButtonProps> = ({
  children,
  className,
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  ...rest
}) => {
  return (
    <button
      className={clsx(
        "admin-btn",
        `admin-btn--${variant}`,
        `admin-btn--${size}`,
        loading && "admin-btn--loading",
        className
      )}
      disabled={loading || disabled}
      {...rest}
    >
      {loading ? "Working…" : children}
    </button>
  );
};

export default Button;
