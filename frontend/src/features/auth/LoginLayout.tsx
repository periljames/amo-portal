import React, { useEffect, useRef, useState } from "react";
import { Eye, EyeOff, ArrowLeft, ArrowRight } from "lucide-react";
import {
  LiquidGlassButton,
  LiquidGlassContainer,
  LiquidGlassLink,
} from "@tinymomentum/liquid-glass-react";
import {
  illustrationFramePreset,
  primaryButtonPreset,
  socialButtonPreset,
} from "../../ui/liquidGlass/presets";
import styles from "./login.module.css";

const DESKTOP_BTN_H = 56;
const MOBILE_BTN_H = 52;
const RECOVERY_LINK_W = 136;
const RECOVERY_LINK_H = 28;
const DESKTOP_SOCIAL_BTN = 52;
const PHONE_SOCIAL_BTN = 48;
const XS_SOCIAL_BTN = 44;
const SOCIAL_RADIUS = 14;

type SocialProvider = "google" | "apple" | "facebook";

type LoginLayoutProps = {
  title: string;
  subtitle: string;
  identifier: string;
  password: string;
  showPassword: boolean;
  showPasswordField: boolean;
  errorMsg: string | null;
  loading: boolean;
  loadingContext: boolean;
  socialAvailability: Record<SocialProvider, boolean>;
  illustrationSrc: string;
  onIdentifierChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onTogglePassword: () => void;
  onForgotPassword: () => void;
  onSwitchAccount?: () => void;
  onFindAmo?: () => void;
  onSocialLogin: (provider: SocialProvider) => void;
  onDemoQuickAccess?: () => void;
};

type GlassIconButtonProps = {
  size: number;
  radius: number;
  className?: string;
  disabled?: boolean;
  ariaLabel: string;
  title: string;
  onClick: () => void;
  children: React.ReactNode;
};

function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState<number | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const node = ref.current;
    const update = () => {
      const next = Math.max(0, Math.round(node.getBoundingClientRect().width));
      setWidth(next || null);
    };

    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return { ref, width };
}

function useResponsiveLoginSizing() {
  const [viewportWidth, setViewportWidth] = useState<number>(() =>
    typeof window !== "undefined" ? window.innerWidth : 1280
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const update = () => setViewportWidth(window.innerWidth);
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const buttonHeight = viewportWidth <= 640 ? MOBILE_BTN_H : DESKTOP_BTN_H;
  const socialButtonSize = viewportWidth <= 400 ? XS_SOCIAL_BTN : viewportWidth <= 640 ? PHONE_SOCIAL_BTN : DESKTOP_SOCIAL_BTN;
  return { buttonHeight, socialButtonSize, viewportWidth };
}

const GlassIconButton: React.FC<GlassIconButtonProps> = ({
  size,
  radius,
  className,
  disabled,
  ariaLabel,
  title,
  onClick,
  children,
}) => {
  return (
    <LiquidGlassContainer
      {...socialButtonPreset}
      width={size}
      height={size}
      borderRadius={radius}
      className={`${styles.socialButton} ${className ?? ""}`.trim()}
    >
      <button
        type="button"
        className={styles.socialButtonInner}
        title={title}
        aria-label={ariaLabel}
        onClick={onClick}
        disabled={disabled}
      >
        {children}
      </button>
    </LiquidGlassContainer>
  );
};

const GoogleIcon: React.FC = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden>
    <path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.9-5.5 3.9-3.3 0-6.1-2.8-6.1-6.2s2.8-6.2 6.1-6.2c1.9 0 3.1.8 3.8 1.5l2.6-2.6C16.9 3 14.7 2 12 2 6.5 2 2 6.5 2 12s4.5 10 10 10c5.8 0 9.6-4 9.6-9.7 0-.7-.1-1.3-.2-1.8H12z" />
  </svg>
);

const AppleIcon: React.FC = () => (
  <svg width="18" height="22" viewBox="0 0 24 24" aria-hidden>
    <path fill="#0b0f16" d="M16.37 1.43c0 1.14-.46 2.2-1.26 3.01-.86.86-2.14 1.49-3.34 1.45-.16-1.12.33-2.32 1.09-3.1.84-.86 2.22-1.48 3.51-1.36zM20.89 17.61c-.5 1.16-.74 1.68-1.38 2.72-.9 1.44-2.17 3.24-3.74 3.26-1.39.02-1.75-.9-3.64-.89-1.89.01-2.28.9-3.67.88-1.57-.02-2.78-1.65-3.68-3.08-2.51-3.95-2.77-8.57-1.22-10.96 1.1-1.7 2.85-2.7 4.49-2.7 1.67 0 2.72.92 4.1.92 1.35 0 2.18-.92 4.08-.92 1.46 0 3.01.79 4.11 2.16-3.61 1.97-3.03 7.08.55 8.61z" />
  </svg>
);

const FacebookIcon: React.FC = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden>
    <circle cx="12" cy="12" r="11" fill="#1D9BF0" />
    <path fill="#fff" d="M13.27 20v-6.66h2.24l.34-2.6h-2.58V9.08c0-.75.2-1.27 1.28-1.27h1.37V5.48c-.24-.03-1.05-.1-2-.1-1.98 0-3.34 1.2-3.34 3.42v1.94H8.34v2.6h2.24V20h2.69z" />
  </svg>
);

const SOCIAL_META: Record<SocialProvider, { icon: React.ReactNode; label: string }> = {
  google: { icon: <GoogleIcon />, label: "Google" },
  apple: { icon: <AppleIcon />, label: "Apple" },
  facebook: { icon: <FacebookIcon />, label: "Facebook" },
};

const LoginLayout: React.FC<LoginLayoutProps> = ({
  title,
  subtitle,
  identifier,
  password,
  showPassword,
  showPasswordField,
  errorMsg,
  loading,
  loadingContext,
  socialAvailability,
  illustrationSrc,
  onIdentifierChange,
  onPasswordChange,
  onSubmit,
  onTogglePassword,
  onForgotPassword,
  onSwitchAccount,
  onFindAmo,
  onSocialLogin,
  onDemoQuickAccess,
}) => {
  const { ref: submitWrapRef, width: submitWrapWidth } = useElementWidth<HTMLDivElement>();
  const { ref: illustrationWrapRef, width: illustrationWidth } = useElementWidth<HTMLDivElement>();
  const { buttonHeight, socialButtonSize, viewportWidth } = useResponsiveLoginSizing();
  const submitButtonWidth = submitWrapWidth ?? Math.min(420, Math.max(220, Math.round(viewportWidth * 0.82)));

  return (
    <div className={styles.pageBg}>
      <div className={styles.bgOrbs} aria-hidden="true">
        <span className={`${styles.blob} ${styles.blobOne}`} />
        <span className={`${styles.blob} ${styles.blobTwo}`} />
        <span className={`${styles.blob} ${styles.blobThree}`} />
      </div>

      <div className={styles.viewportContent}>
        <div className={styles.shell}>
          <div className={styles.shellSurface}>
            <div className={styles.shellInnerGrid}>
            <section className={styles.left}>
              <h1 className={styles.title}>{title}</h1>
              <p className={styles.subtitle}>{subtitle}</p>

              <form className={styles.form} onSubmit={onSubmit} noValidate>
                {errorMsg ? <p className={styles.error}>{errorMsg}</p> : null}

                <label htmlFor="identifier" className={styles.label}>Email</label>
                <input
                  id="identifier"
                  className={styles.input}
                  type="email"
                  autoComplete="username"
                  placeholder="Email"
                  value={identifier}
                  onChange={(event) => onIdentifierChange(event.target.value)}
                  required
                />

                {showPasswordField ? (
                  <>
                    <label htmlFor="password" className={styles.label}>Password</label>
                    <div className={styles.passwordWrap}>
                      <input
                        id="password"
                        className={styles.passwordInput}
                        type={showPassword ? "text" : "password"}
                        autoComplete="current-password"
                        placeholder="Password"
                        value={password}
                        onChange={(event) => onPasswordChange(event.target.value)}
                        required
                      />
                      <button type="button" className={styles.eyeBtn} aria-label="Toggle password visibility" onClick={onTogglePassword}>
                        {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                      </button>
                    </div>

                    <div className={styles.recoveryRow}>
                      <LiquidGlassLink
                        {...socialButtonPreset}
                        width={RECOVERY_LINK_W}
                        height={RECOVERY_LINK_H}
                        borderRadius={10}
                        href="#"
                        className={styles.recoveryLink}
                        onClick={(event) => {
                          event.preventDefault();
                          onForgotPassword();
                        }}
                      >
                        Recovery Password
                      </LiquidGlassLink>
                    </div>
                  </>
                ) : null}

                <div className={styles.submitButtonWrap} ref={submitWrapRef}>
                  <LiquidGlassButton
                    {...primaryButtonPreset}
                    width={submitButtonWidth}
                    height={buttonHeight}
                    borderRadius={12}
                    type="submit"
                    className={styles.submitButton}
                    disabled={loading || loadingContext}
                  >
                    {showPasswordField ? (loading ? "Signing In..." : "Sign In") : (loadingContext ? "Checking..." : "Continue")}
                  </LiquidGlassButton>
                </div>

                <div className={styles.dividerRow}>
                  <span className={styles.dividerLine} />
                  <span className={styles.dividerText}>Or continue with</span>
                  <span className={styles.dividerLine} />
                </div>

                <div className={styles.socialRow}>
                  {(Object.keys(SOCIAL_META) as SocialProvider[]).map((provider) => (
                    <GlassIconButton
                      key={provider}
                      size={socialButtonSize}
                      radius={SOCIAL_RADIUS}
                      className={provider === "apple" ? styles.socialButtonActive : ""}
                      title={SOCIAL_META[provider].label}
                      ariaLabel={SOCIAL_META[provider].label}
                      onClick={() => onSocialLogin(provider)}
                      disabled={!socialAvailability[provider] || loading || loadingContext}
                    >
                      {SOCIAL_META[provider].icon}
                    </GlassIconButton>
                  ))}
                </div>

                {(onSwitchAccount || onFindAmo || onDemoQuickAccess) ? (
                  <div className={styles.switchRow}>
                    {onSwitchAccount ? <button type="button" className={styles.switchBtn} onClick={onSwitchAccount}>Use a different account</button> : <span />}
                    {onFindAmo ? <button type="button" className={styles.switchBtn} onClick={onFindAmo}>Find your AMO</button> : null}
                    {onDemoQuickAccess ? <button type="button" className={styles.switchBtn} onClick={onDemoQuickAccess}>Use Demo Access</button> : null}
                  </div>
                ) : null}
              </form>
            </section>

            <aside className={styles.right} ref={illustrationWrapRef}>
              <LiquidGlassContainer
                {...illustrationFramePreset}
                className={styles.illustrationFrame}
                width={illustrationWidth ?? Math.min(520, Math.max(260, Math.round(viewportWidth * 0.84)))}
              >
                <img src={illustrationSrc} alt="Winter landscape illustration" className={styles.illustration} />
                <div className={styles.illustrationOverlay}>
                  <p className={styles.overlayText}>Finally, all your work in one place.</p>
                  <div className={styles.overlayControls}>
                    <button type="button" className={styles.circleBtn} aria-label="Previous">
                      <ArrowLeft size={18} />
                    </button>
                    <button type="button" className={styles.circleBtn} aria-label="Next">
                      <ArrowRight size={18} />
                    </button>
                  </div>
                </div>
              </LiquidGlassContainer>
            </aside>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginLayout;
