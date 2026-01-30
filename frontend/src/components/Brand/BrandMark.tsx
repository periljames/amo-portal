// src/components/Brand/BrandMark.tsx
import React, { useEffect, useMemo, useState } from "react";
import { BrandContext } from "./BrandContext";

type BrandMarkProps = {
  name?: string;
  logoUrl?: string | null;
  size?: number;
  className?: string;
};

const getInitials = (name: string): string => {
  const parts = name
    .split(/\\s+/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) return "AM";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
};

export const BrandMark: React.FC<BrandMarkProps> = ({
  name,
  logoUrl,
  size = 40,
  className,
}) => {
  const branding = React.useContext(BrandContext);
  const [logoFailed, setLogoFailed] = useState(false);

  const displayName = (name || branding.name || "AMO Portal").trim();
  const initials = useMemo(() => getInitials(displayName), [displayName]);
  const resolvedLogo = logoUrl ?? branding.logoUrl ?? null;
  const showLogo = !!resolvedLogo && !logoFailed;

  useEffect(() => {
    setLogoFailed(false);
  }, [resolvedLogo]);

  return (
    <div className={`brand-mark ${className || ""}`} style={{ width: size, height: size }}>
      {showLogo ? (
        <img
          src={resolvedLogo}
          alt={`${displayName} logo`}
          className="brand-mark__logo"
          onError={() => setLogoFailed(true)}
        />
      ) : (
        <svg
          className="brand-mark__placeholder"
          viewBox="0 0 64 64"
          role="img"
          aria-label={`${displayName} mark`}
        >
          <circle cx="32" cy="32" r="28" />
          <path
            d="M20 42V22c0-1.7 1.3-3 3-3h10c6.6 0 12 5.4 12 12s-5.4 12-12 12H20z"
            opacity="0.08"
          />
          <text x="32" y="38" textAnchor="middle">
            {initials}
          </text>
        </svg>
      )}
    </div>
  );
};
