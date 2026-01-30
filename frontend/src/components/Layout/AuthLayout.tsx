// src/components/Layout/AuthLayout.tsx
import React from "react";
import { BrandContext } from "../Brand/BrandContext";
import { BrandMark } from "../Brand/BrandMark";
import { BrandProvider } from "../Brand/BrandProvider";

interface AuthLayoutProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  brandName?: string | null;
}

const AuthLayout: React.FC<AuthLayoutProps> = ({
  title,
  subtitle,
  children,
  brandName,
}) => {
  return (
    <BrandProvider nameOverride={brandName} preferStoredName={false}>
      <BrandContext.Consumer>
        {(brand) => (
          <div className="auth-layout">
            <div className="auth-layout__card" role="main">
              <div className="auth-layout__brand">
                <BrandMark size={48} />
                <div>
                  <div className="auth-layout__brand-name">{brand.name}</div>
                  <div className="auth-layout__brand-subtitle">AMO Portal</div>
                </div>
              </div>

              <h1 className="auth-layout__title">{title}</h1>

              {subtitle && <p className="auth-layout__subtitle">{subtitle}</p>}

              {children}
            </div>
          </div>
        )}
      </BrandContext.Consumer>
    </BrandProvider>
  );
};

export default AuthLayout;
