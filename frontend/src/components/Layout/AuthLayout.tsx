// src/components/Layout/AuthLayout.tsx
import React from "react";

interface AuthLayoutProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

const AuthLayout: React.FC<AuthLayoutProps> = ({
  title,
  subtitle,
  children,
}) => {
  return (
    <div className="auth-layout">
      <div className="auth-layout__card">
        <div className="auth-layout__badge">
          <span>AMO PORTAL</span>
        </div>
        <h1 className="auth-layout__title">{title}</h1>
        {subtitle && (
          <p className="auth-layout__subtitle">{subtitle}</p>
        )}
        {children}
      </div>
    </div>
  );
};

export default AuthLayout;
