// src/pages/LoginPage.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Apple, Chrome, Mail } from "lucide-react";
import AuthLayout from "../components/Layout/AuthLayout";
import {
  fetchOnboardingStatus,
  getCachedUser,
  getContext,
  getLastLoginIdentifier,
  getLoginContext,
  getToken,
  login,
  type LoginContextResponse,
  type OnboardingStatus,
  type PortalUser,
} from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";
import { GlassButton, GlassCard } from "../ui/liquidGlass";

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PLATFORM_SUPPORT_SLUG = "system";

type LoginStep = "identify" | "password";
type SocialProvider = "google" | "outlook" | "apple";

type SocialConfig = {
  icon: React.ComponentType<{ size?: number }>;
  url: string | undefined;
  title: string;
};

const SOCIAL_AUTH_CONFIG: Record<SocialProvider, SocialConfig> = {
  google: { icon: Chrome, url: import.meta.env.VITE_AUTH_GOOGLE_URL, title: "Google" },
  outlook: { icon: Mail, url: import.meta.env.VITE_AUTH_OUTLOOK_URL, title: "Outlook" },
  apple: { icon: Apple, url: import.meta.env.VITE_AUTH_APPLE_URL, title: "Apple" },
};

function isAdminUser(u: PortalUser | null): boolean {
  if (!u) return false;
  return !!u.is_superuser || !!u.is_amo_admin || u.role === "SUPERUSER" || u.role === "AMO_ADMIN";
}

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { amoCode } = useParams<{ amoCode?: string }>();

  const cachedIdentifier = getLastLoginIdentifier();
  const defaultIdentifier = import.meta.env.DEV && !amoCode ? "admin@amo.local" : "";
  const [identifier, setIdentifier] = useState(cachedIdentifier || defaultIdentifier);
  const [password, setPassword] = useState(import.meta.env.DEV ? "ChangeMe123!" : "");
  const [rememberMe, setRememberMe] = useState(true);

  const [loading, setLoading] = useState(false);
  const [loadingContext, setLoadingContext] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loginContext, setLoginContext] = useState<LoginContextResponse | null>(
    amoCode
      ? {
          login_slug: amoCode,
          amo_code: null,
          amo_name: decodeAmoCertFromUrl(amoCode),
          is_platform: false,
        }
      : null
  );
  const [step, setStep] = useState<LoginStep>(amoCode ? "password" : "identify");
  const redirectedRef = useRef(false);

  const fromState = (location.state as { from?: string } | null)?.from;

  const effectiveAmoSlug = useMemo(() => loginContext?.login_slug ?? "", [loginContext?.login_slug]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let active = true;

    const run = async () => {
      const ctx = getContext();
      const slug = effectiveAmoSlug || ctx.amoSlug || amoCode || PLATFORM_SUPPORT_SLUG;
      if (!slug || !active) return;

      const u = getCachedUser();
      const admin = isAdminUser(u);
      let onboardingStatus: OnboardingStatus | null = null;
      try {
        onboardingStatus = await fetchOnboardingStatus();
      } catch (err) {
        console.warn("Onboarding status fetch failed:", err);
      }
      const requiresOnboarding = onboardingStatus ? !onboardingStatus.is_complete : !!u?.must_change_password;
      if (requiresOnboarding && !redirectedRef.current) {
        redirectedRef.current = true;
        navigate(`/maintenance/${slug}/onboarding/setup`, { replace: true });
        return;
      }
      if (fromState) {
        navigate(fromState, { replace: true });
        return;
      }
      const landingDept = admin ? "admin" : (ctx.department || null);
      if (!admin && !landingDept) {
        setErrorMsg("Your account is missing a department assignment. Please contact the AMO Administrator or Quality/IT.");
        return;
      }
      navigate(admin ? `/maintenance/${slug}/admin/overview` : `/maintenance/${slug}/${landingDept}`, { replace: true });
    };

    void run();
    return () => {
      active = false;
    };
  }, [amoCode, effectiveAmoSlug, fromState, navigate]);

  const handleIdentify = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMsg(null);
    const trimmedIdentifier = identifier.trim();
    if (!trimmedIdentifier) {
      setErrorMsg("Enter your work email or staff ID.");
      return;
    }
    if (trimmedIdentifier.includes("@") && !emailRegex.test(trimmedIdentifier)) {
      setErrorMsg("Enter a valid email address.");
      return;
    }
    try {
      setLoadingContext(true);
      const context = await getLoginContext(trimmedIdentifier);
      setLoginContext(context);
      setStep("password");
    } catch (err: unknown) {
      console.error("Login context error:", err);
      setErrorMsg(err instanceof Error ? err.message : "Could not find your account.");
    } finally {
      setLoadingContext(false);
    }
  };

  const resetContext = () => {
    if (amoCode) return;
    setLoginContext(null);
    setStep("identify");
    setPassword("");
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMsg(null);

    const trimmedIdentifier = identifier.trim();
    if (!trimmedIdentifier || !password) {
      setErrorMsg("Enter your email or staff ID and password.");
      return;
    }
    if (trimmedIdentifier.includes("@") && !emailRegex.test(trimmedIdentifier)) {
      setErrorMsg("Enter a valid email address.");
      return;
    }
    if (!effectiveAmoSlug.trim()) {
      setErrorMsg("We could not determine your login context. Start again.");
      return;
    }

    try {
      setLoading(true);
      const slugToUse = effectiveAmoSlug.trim();
      const auth = await login(slugToUse, trimmedIdentifier, password);

      let onboardingStatus: OnboardingStatus | null = null;
      try {
        onboardingStatus = await fetchOnboardingStatus({ force: true });
      } catch (err) {
        console.warn("Onboarding status fetch failed:", err);
      }
      const requiresOnboarding = onboardingStatus ? !onboardingStatus.is_complete : !!auth.user?.must_change_password;
      if (requiresOnboarding && !redirectedRef.current) {
        redirectedRef.current = true;
        navigate(`/maintenance/${slugToUse}/onboarding/setup`, { replace: true });
        return;
      }
      if (fromState) {
        navigate(fromState, { replace: true });
        return;
      }

      const ctx = getContext();
      const admin = isAdminUser(getCachedUser());
      if (!admin) {
        if (!ctx.department) {
          setErrorMsg("Your account is missing a department assignment. Please contact the AMO Administrator or Quality/IT.");
          return;
        }
        navigate(`/maintenance/${slugToUse}/${ctx.department}`, { replace: true });
        return;
      }
      navigate(`/maintenance/${slugToUse}/admin/overview`, { replace: true });
    } catch (err: unknown) {
      console.error("Login error:", err);
      const msg = err instanceof Error ? err.message.toLowerCase() : "";
      if (msg.includes("locked")) {
        setErrorMsg("Your account is locked due to repeated failed attempts. Contact Quality or IT support.");
      } else if (msg.includes("401") || msg.includes("unauthorized") || msg.includes("invalid credentials") || msg.includes("incorrect")) {
        setErrorMsg("Invalid email or password.");
      } else if (msg.includes("not found") || msg.includes("amo")) {
        setErrorMsg("AMO not found. Check the portal link or contact support.");
      } else {
        setErrorMsg("Could not sign in. Try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const amoSlugForLabel = loginContext?.login_slug || amoCode || null;
  const brandName = loginContext?.amo_name || (amoSlugForLabel ? decodeAmoCertFromUrl(amoSlugForLabel) : null);

  const handleSocialLogin = (provider: SocialProvider) => {
    const target = SOCIAL_AUTH_CONFIG[provider].url;
    if (!target) {
      setErrorMsg(`${SOCIAL_AUTH_CONFIG[provider].title} login is not configured.`);
      return;
    }
    const amoHint = amoSlugForLabel ? `?amo=${encodeURIComponent(amoSlugForLabel)}` : "";
    window.location.assign(`${target}${amoHint}`);
  };

  return (
    <AuthLayout title="Login" brandName={brandName} className="auth-layout--aviation auth-layout--liquid">
      <GlassCard preset="loginCard" className="auth-liquid-card" padding={24}>
        <form className="auth-form" onSubmit={step === "identify" ? handleIdentify : handleSubmit} noValidate>
          {errorMsg ? <div className="auth-form__error" role="alert">{errorMsg}</div> : null}
          <p className="auth-form__portal-note">Secure AMO access</p>

          <div className="auth-form__field">
            <label htmlFor="identifier" className="sr-only">Email or staff ID</label>
            <input
              id="identifier"
              className="glass-input"
              type="text"
              autoComplete="username"
              name="identifier"
              placeholder="Email or staff ID"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              required
            />
          </div>

          {step === "password" ? (
            <div className="auth-form__field">
              <label htmlFor="password" className="sr-only">Password</label>
              <input
                id="password"
                className="glass-input"
                type="password"
                autoComplete="current-password"
                name="password"
                placeholder="Password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
          ) : null}

          <div className="auth-form__meta-row">
            <label className="auth-form__remember">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(event) => setRememberMe(event.target.checked)}
              />
              <span>Remember</span>
            </label>
            <button
              type="button"
              className="auth-form__link"
              onClick={() => {
                const query = amoSlugForLabel ? `?amo=${amoSlugForLabel}` : "";
                navigate(`/reset-password${query}`);
              }}
            >
              Forgot password?
            </button>
          </div>

          {step === "password" && !amoCode ? (
            <button type="button" className="auth-form__link" onClick={resetContext} disabled={loading}>
              Switch account
            </button>
          ) : null}

          {amoCode ? (
            <button
              type="button"
              className="auth-form__link"
              onClick={() => navigate("/login")}
              disabled={loading || loadingContext}
            >
              Find your AMO
            </button>
          ) : null}

          <div className="auth-form__actions">
            {step === "identify" ? (
              <GlassButton type="submit" disabled={loadingContext} className="auth-form__primary" glassProps={{ width: 320, height: 52 }}>
                {loadingContext ? "Checking…" : "Continue"}
              </GlassButton>
            ) : (
              <GlassButton type="submit" disabled={loading} className="auth-form__primary" glassProps={{ width: 320, height: 52 }}>
                {loading ? "Signing in…" : "Login"}
              </GlassButton>
            )}
          </div>

          <div className="login-social-icons" role="group" aria-label="Social sign in">
            {(Object.keys(SOCIAL_AUTH_CONFIG) as SocialProvider[]).map((provider) => {
              const item = SOCIAL_AUTH_CONFIG[provider];
              const Icon = item.icon;
              return (
                <GlassButton
                  key={provider}
                  type="button"
                  onClick={() => handleSocialLogin(provider)}
                  title={item.url ? item.title : `${item.title} not configured`}
                  aria-label={item.title}
                  disabled={!item.url || loading || loadingContext}
                  className="auth-social__icon-btn"
                  glassProps={{ width: 44, height: 44, borderRadius: 22, glassTintOpacity: 36, noiseStrength: 46 }}
                >
                  <Icon size={18} />
                </GlassButton>
              );
            })}
          </div>

        </form>
      </GlassCard>
    </AuthLayout>
  );
};

export default LoginPage;
