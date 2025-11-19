import React from "react";
import { clsx } from "clsx";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
}

const Button: React.FC<ButtonProps> = ({ children, loading, className, ...rest }) => {
  return (
    <button
      className={clsx("btn", loading && "btn--loading", className)}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading ? "Please wait..." : children}
    </button>
  );
};

export default Button;
