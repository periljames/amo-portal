import React, { useEffect, useState } from "react";
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
  const [logoFailed, setLogoFailed] = useState(false);
  const [resolvedScheme, setResolvedScheme] = useState<"dark" | "light">("dark");
  const resolvedSubtitle = subtitle.toUpperCase();

  useEffect(() => {
    const readScheme = () => {
      const scheme = document.body.dataset.colorScheme;
      setResolvedScheme(scheme === "light" ? "light" : "dark");
    };
    readScheme();
    const observer = new MutationObserver(readScheme);
    observer.observe(document.body, { attributes: true, attributeFilter: ["data-color-scheme"] });
    return () => observer.disconnect();
  }, []);

  const preferredLogo =
    resolvedScheme === "dark"
      ? brand.logoUrlDark || brand.logoUrl || brand.logoUrlLight
      : brand.logoUrlLight || brand.logoUrl || brand.logoUrlDark;

  useEffect(() => {
    setLogoFailed(false);
  }, [preferredLogo]);

  const showFullTopbarLogo = variant === "topbar" && preferredLogo && !logoFailed;

  return (
    <div className={`brand-header brand-header--${variant} ${className || ""}`.trim()}>
      {showFullTopbarLogo ? (
        <div className="brand-header__topbar-logo-wrap">
          <img
            src={preferredLogo}
            alt={`${brand.name} logo`}
            className="brand-header__topbar-logo"
            onError={() => setLogoFailed(true)}
          />
        </div>
      ) : (
        <>
          <BrandLogo size={variant === "auth" ? 48 : 32} className="brand-header__logo" />
          <div className="brand-header__text">
            <span className="brand-header__name">{brand.name}</span>
            <span className="brand-header__subtitle">{resolvedSubtitle}</span>
          </div>
        </>
      )}
    </div>
  );
};
