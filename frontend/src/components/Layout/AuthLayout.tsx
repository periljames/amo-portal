// src/components/Layout/AuthLayout.tsx
import React from "react";
import { BrandContext } from "../Brand/BrandContext";
import { BrandHeader } from "../Brand/BrandHeader";
import { BrandProvider } from "../Brand/BrandProvider";

interface AuthLayoutProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  brandName?: string | null;
  className?: string;
}

const AuthLayout: React.FC<AuthLayoutProps> = ({
  title,
  subtitle,
  children,
  brandName,
  className,
}) => {
  const wallpaperVideo = import.meta.env.VITE_AUTH_WALLPAPER_VIDEO;
  const wallpaperDesktop = import.meta.env.VITE_AUTH_WALLPAPER_IMAGE_DESKTOP;
  const wallpaperTablet = import.meta.env.VITE_AUTH_WALLPAPER_IMAGE_TABLET;
  const wallpaperMobile = import.meta.env.VITE_AUTH_WALLPAPER_IMAGE_MOBILE;

  return (
    <BrandProvider nameOverride={brandName} preferStoredName={false}>
      <BrandContext.Consumer>
        {() => (
          <div className={`auth-layout ${className ?? ""}`.trim()}>
            <div className="auth-layout__scene" aria-hidden>
              {wallpaperVideo ? (
                <video
                  className="auth-layout__video"
                  autoPlay
                  muted
                  loop
                  playsInline
                  poster={wallpaperDesktop || undefined}
                >
                  <source src={wallpaperVideo} type="video/mp4" />
                </video>
              ) : null}
              <picture className="auth-layout__wallpaper">
                {wallpaperMobile ? <source media="(max-width: 640px)" srcSet={wallpaperMobile} /> : null}
                {wallpaperTablet ? <source media="(max-width: 1024px)" srcSet={wallpaperTablet} /> : null}
                {wallpaperDesktop ? <img src={wallpaperDesktop} alt="" loading="eager" /> : null}
              </picture>
              <div className="auth-layout__aurora" />
              <div className="auth-layout__noise" />
            </div>
            <div className="auth-layout__card" role="main">
              <div className="auth-layout__brand">
                <BrandHeader variant="auth" />
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
