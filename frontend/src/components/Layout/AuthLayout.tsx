import React from "react";

interface AuthLayoutProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

const AuthLayout: React.FC<AuthLayoutProps> = ({ title, subtitle, children }) => {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-card__header">
          <div className="auth-logo">AMO Portal</div>
          <h1 className="auth-title">{title}</h1>
          {subtitle && <p className="auth-subtitle">{subtitle}</p>}
        </div>
        <div className="auth-card__body">{children}</div>
        <div className="auth-card__footer">
          <p>© {new Date().getFullYear()} Safarilink AMO · Internal Use Only</p>
        </div>
      </div>
    </div>
  );
};

export default AuthLayout;
