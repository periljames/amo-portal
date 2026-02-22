// src/pages/LoginPage.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import LoginLayout from "../features/auth/LoginLayout";
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

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PLATFORM_SUPPORT_SLUG = "system";

const DEMO_AMO_SLUG = (import.meta.env.VITE_DEMO_AMO_SLUG || "demo-amo").trim();
const DEMO_LOGIN_EMAIL = (import.meta.env.VITE_DEMO_LOGIN_EMAIL || "admin@demo.example.com").trim();
const DEMO_LOGIN_PASSWORD = (import.meta.env.VITE_DEMO_LOGIN_PASSWORD || "ChangeMe123!").trim();

const MAX_SUBTITLE_WORDS = 8;

function sanitizeBriefMessage(message: string | null | undefined): string | null {
  if (!message) return null;
  const words = message.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return null;
  return words.slice(0, MAX_SUBTITLE_WORDS).join(" ");
}

function getDynamicLoginSubtitle(now: Date): string {
  const platformFocus = sanitizeBriefMessage(
    typeof window !== "undefined" ? window.localStorage.getItem("amodb:login-focus") : null
  );
  if (platformFocus) return platformFocus;

  const envFocus = sanitizeBriefMessage(import.meta.env.VITE_LOGIN_FOCUS_MESSAGE as string | undefined);
  if (envFocus) return envFocus;

  const day = now.getDate();
  const hour = now.getHours();

  if (day >= 25 || day <= 2) return "Payroll week: review dues and approvals";
  if (hour < 10) return "Morning checks: review critical operations";
  if (hour < 15) return "Priority updates require your quick review";
  return "End-of-day: close pending critical items";
}

type LoginStep = "identify" | "password";
type SocialProvider = "google" | "apple" | "facebook";

type SocialConfig = {
  url: string | undefined;
  title: string;
};

const SOCIAL_AUTH_CONFIG: Record<SocialProvider, SocialConfig> = {
  google: { url: import.meta.env.VITE_AUTH_GOOGLE_URL, title: "Google" },
  apple: { url: import.meta.env.VITE_AUTH_APPLE_URL, title: "Apple" },
  facebook: { url: import.meta.env.VITE_AUTH_FACEBOOK_URL, title: "Facebook" },
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
  const [showPassword, setShowPassword] = useState(false);

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

  const handleIdentify = async () => {
    setErrorMsg(null);
    const trimmedIdentifier = identifier.trim();

    if (!trimmedIdentifier) {
      setErrorMsg("Enter your work email.");
      return;
    }
    if (!emailRegex.test(trimmedIdentifier)) {
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

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (step === "identify") {
      await handleIdentify();
      return;
    }

    setErrorMsg(null);
    const trimmedIdentifier = identifier.trim();
    if (!trimmedIdentifier || !password) {
      setErrorMsg("Enter your email and password.");
      return;
    }
    if (!emailRegex.test(trimmedIdentifier)) {
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

  const resetContext = () => {
    if (amoCode) return;
    setLoginContext(null);
    setStep("identify");
    setPassword("");
  };

  const amoSlugForLabel = loginContext?.login_slug || amoCode || null;

  const handleSocialLogin = (provider: SocialProvider) => {
    const target = SOCIAL_AUTH_CONFIG[provider].url;
    if (!target) {
      setErrorMsg(`${SOCIAL_AUTH_CONFIG[provider].title} login is not configured.`);
      return;
    }
    const amoHint = amoSlugForLabel ? `?amo=${encodeURIComponent(amoSlugForLabel)}` : "";
    window.location.assign(`${target}${amoHint}`);
  };

  const handleDemoQuickAccess = () => {
    setLoginContext({
      login_slug: DEMO_AMO_SLUG,
      amo_code: "DEMO",
      amo_name: "Demo AMO",
      is_platform: false,
    });
    setIdentifier(DEMO_LOGIN_EMAIL);
    setPassword(DEMO_LOGIN_PASSWORD);
    setStep("password");
    setErrorMsg(null);
  };

  const illustrationSrc =
    import.meta.env.VITE_AUTH_ILLUSTRATION_IMAGE ||
    import.meta.env.VITE_AUTH_WALLPAPER_IMAGE_DESKTOP ||
    "/login-illustration-placeholder.svg";

  const subtitle = useMemo(() => getDynamicLoginSubtitle(new Date()), []);

  return (
    <LoginLayout
      title="Hello Again!"
      subtitle={subtitle}
      identifier={identifier}
      password={password}
      showPassword={showPassword}
      showPasswordField={step === "password"}
      errorMsg={errorMsg}
      loading={loading}
      loadingContext={loadingContext}
      socialAvailability={{
        google: !!SOCIAL_AUTH_CONFIG.google.url,
        apple: !!SOCIAL_AUTH_CONFIG.apple.url,
        facebook: !!SOCIAL_AUTH_CONFIG.facebook.url,
      }}
      illustrationSrc={illustrationSrc}
      onIdentifierChange={setIdentifier}
      onPasswordChange={setPassword}
      onSubmit={handleSubmit}
      onTogglePassword={() => setShowPassword((prev) => !prev)}
      onForgotPassword={() => {
        const query = amoSlugForLabel ? `?amo=${amoSlugForLabel}` : "";
        navigate(`/reset-password${query}`);
      }}
      onSwitchAccount={step === "password" && !amoCode ? resetContext : undefined}
      onFindAmo={amoCode ? () => navigate("/login") : undefined}
      onSocialLogin={handleSocialLogin}
      onDemoQuickAccess={!amoCode ? handleDemoQuickAccess : undefined}
    />
  );
};

export default LoginPage;
