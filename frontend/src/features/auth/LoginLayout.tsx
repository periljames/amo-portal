import React from "react";
import { Eye, EyeOff, ArrowLeft, ArrowRight } from "lucide-react";
import {
  LiquidGlassButton,
  LiquidGlassContainer,
  LiquidGlassLink,
} from "@tinymomentum/liquid-glass-react";
import {
  illustrationFramePreset,
  outerShellPreset,
  primaryButtonPreset,
  socialButtonPreset,
} from "../../ui/liquidGlass/presets";
import styles from "./login.module.css";

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
};

const GoogleIcon: React.FC = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden>
    <path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.9-5.5 3.9-3.3 0-6.1-2.8-6.1-6.2s2.8-6.2 6.1-6.2c1.9 0 3.1.8 3.8 1.5l2.6-2.6C16.9 3 14.7 2 12 2 6.5 2 2 6.5 2 12s4.5 10 10 10c5.8 0 9.6-4 9.6-9.7 0-.7-.1-1.3-.2-1.8H12z" />
  </svg>
);

const AppleIcon: React.FC = () => (
  <svg width="20" height="24" viewBox="0 0 24 24" aria-hidden>
    <path fill="currentColor" d="M16.37 1.43c0 1.14-.46 2.2-1.26 3.01-.86.86-2.14 1.49-3.34 1.45-.16-1.12.33-2.32 1.09-3.1.84-.86 2.22-1.48 3.51-1.36zM20.89 17.61c-.5 1.16-.74 1.68-1.38 2.72-.9 1.44-2.17 3.24-3.74 3.26-1.39.02-1.75-.9-3.64-.89-1.89.01-2.28.9-3.67.88-1.57-.02-2.78-1.65-3.68-3.08-2.51-3.95-2.77-8.57-1.22-10.96 1.1-1.7 2.85-2.7 4.49-2.7 1.67 0 2.72.92 4.1.92 1.35 0 2.18-.92 4.08-.92 1.46 0 3.01.79 4.11 2.16-3.61 1.97-3.03 7.08.55 8.61z"/>
  </svg>
);

const FacebookIcon: React.FC = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden>
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
}) => {
  return (
    <div className={styles.pageBg}>
      <LiquidGlassContainer {...outerShellPreset} className={styles.shell}>
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
                    required={showPasswordField}
                    disabled={!showPasswordField}
                  />
                  <button type="button" className={styles.eyeBtn} aria-label="Toggle password visibility" onClick={onTogglePassword}>
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>

                <div className={styles.recoveryRow}>
                  <LiquidGlassLink {...socialButtonPreset} href="#" className={styles.recoveryLink} onClick={(event) => { event.preventDefault(); onForgotPassword(); }}>
                    Recovery Password
                  </LiquidGlassLink>
                </div>

                <LiquidGlassButton
                  {...primaryButtonPreset}
                  type="submit"
                  className={styles.submitButton}
                  disabled={loading || loadingContext}
                >
                  {loading ? "Signing In..." : loadingContext ? "Checking..." : "Sign In"}
                </LiquidGlassButton>

                <div className={styles.dividerRow}>
                  <span className={styles.dividerLine} />
                  <span className={styles.dividerText}>Or continue with</span>
                  <span className={styles.dividerLine} />
                </div>

                <div className={styles.socialRow}>
                  {(Object.keys(SOCIAL_META) as SocialProvider[]).map((provider) => (
                    <LiquidGlassContainer
                      key={provider}
                      {...socialButtonPreset}
                      className={`${styles.socialButton} ${provider === "apple" ? styles.socialButtonActive : ""}`.trim()}
                    >
                      <button
                        type="button"
                        className={styles.socialButtonInner}
                        title={SOCIAL_META[provider].label}
                        aria-label={SOCIAL_META[provider].label}
                        onClick={() => onSocialLogin(provider)}
                        disabled={!socialAvailability[provider] || loading || loadingContext}
                      >
                        {SOCIAL_META[provider].icon}
                      </button>
                    </LiquidGlassContainer>
                  ))}
                </div>

                {(onSwitchAccount || onFindAmo) ? (
                  <div className={styles.switchRow}>
                    {onSwitchAccount ? <button type="button" className={styles.switchBtn} onClick={onSwitchAccount}>Use a different account</button> : <span />}
                    {onFindAmo ? <button type="button" className={styles.switchBtn} onClick={onFindAmo}>Find your AMO</button> : null}
                  </div>
                ) : null}
              </form>
            </section>

            <aside className={styles.right}>
              <LiquidGlassContainer {...illustrationFramePreset} className={styles.illustrationFrame}>
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
      </LiquidGlassContainer>
    </div>
  );
};

export default LoginLayout;
