import React from "react";
import { BrandContext } from "./BrandContext";
import { BrandLogo } from "./BrandLogo";

type BrandHeaderVariant = "sidebar" | "topbar" | "auth";

type BrandHeaderProps = {
  variant?: BrandHeaderVariant;
  className?: string;
  subtitle?: string;
};

export const BrandHeader: React.FC<BrandHeaderProps> = ({
  variant = "sidebar",
  className,
  subtitle = "AMO PORTAL",
}) => {
  const brand = React.useContext(BrandContext);
  const resolvedSubtitle = subtitle.toUpperCase();
  return (
    <div className={`brand-header brand-header--${variant} ${className || ""}`.trim()}>
      <BrandLogo size={variant === "auth" ? 48 : 32} className="brand-header__logo" />
      <div className="brand-header__text">
        <span className="brand-header__name">{brand.name}</span>
        <span className="brand-header__subtitle">{resolvedSubtitle}</span>
      </div>
    </div>
  );
};
