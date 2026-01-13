// src/pages/LoginPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useLocation, useParams } from "react-router-dom";
import AuthLayout from "../components/Layout/AuthLayout";
import TextField from "../components/UI/TextField";
import Button from "../components/UI/Button";
import {
  login,
  getToken,
  getCachedUser,
  getContext,
  getLoginContext,
  type LoginContextResponse,
} from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Platform support slug (superuser login)
const PLATFORM_SUPPORT_SLUG = "system";

type LoginStep = "identify" | "password";

function isAdminUser(u: any): boolean {
  if (!u) return false;
  return (
    !!u.is_superuser ||
    !!u.is_amo_admin ||
    u.role === "SUPERUSER" ||
    u.role === "AMO_ADMIN"
  );
}

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { amoCode } = useParams<{ amoCode?: string }>();

  const [email, setEmail] = useState(import.meta.env.DEV ? "admin@amo.local" : "");
  const [password, setPassword] = useState(import.meta.env.DEV ? "ChangeMe123!" : "");

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

  const fromState = (location.state as { from?: string } | null)?.from;

  const effectiveAmoSlug = useMemo(() => {
    if (loginContext?.login_slug) return loginContext.login_slug;
    return "";
  }, [loginContext?.login_slug]);

  // If already logged in, bounce straight to dashboard
  useEffect(() => {
    const token = getToken();
    if (!token) return;

    const ctx = getContext();
    const slug =
      effectiveAmoSlug || ctx.amoSlug || amoCode || PLATFORM_SUPPORT_SLUG;

    if (!slug) return;
    const u = getCachedUser();
    const admin = isAdminUser(u);

    if (u?.must_change_password) {
      navigate(`/maintenance/${slug}/onboarding`, { replace: true });
      return;
    }

    // If router gave us a "from" location, respect it
    if (fromState) {
      navigate(fromState, { replace: true });
      return;
    }

    // Normal users MUST go to server-assigned department
    const landingDept = admin ? (ctx.department || "admin") : (ctx.department || null);

    if (!admin && !landingDept) {
      // Stay on login and show a clean error
      setErrorMsg(
        "Your account is missing a department assignment. Please contact the AMO Administrator or Quality/IT."
      );
      return;
    }

    navigate(`/maintenance/${slug}/${landingDept}`, { replace: true });
  }, [navigate, fromState, amoCode, effectiveAmoSlug]);

  const handleIdentify = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setErrorMsg("Please enter your work email.");
      return;
    }
    if (!emailRegex.test(trimmedEmail)) {
      setErrorMsg("Please enter a valid email address.");
      return;
    }

    try {
      setLoadingContext(true);
      const context = await getLoginContext(trimmedEmail);
      setLoginContext(context);
      setStep("password");
    } catch (err: unknown) {
      console.error("Login context error:", err);
      const msg = err instanceof Error ? err.message : "Could not find your account.";
      setErrorMsg(msg);
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      setErrorMsg("Please enter both email and password.");
      return;
    }
    if (!emailRegex.test(trimmedEmail)) {
      setErrorMsg("Please enter a valid email address.");
      return;
    }

    if (!effectiveAmoSlug) {
      setErrorMsg(
        "We could not determine your login context. Please start again."
      );
      return;
    }

    const slugToUse = effectiveAmoSlug.trim();
    if (!slugToUse) {
      setErrorMsg(
        "We could not determine your login context. Please start again."
      );
      return;
    }

    try {
      setLoading(true);

      // login() stores:
      // - token
      // - server-provided AMO + department context
      // - cached user
      const auth = await login(slugToUse, trimmedEmail, password);

      if (auth.user?.must_change_password) {
        navigate(`/maintenance/${slugToUse}/onboarding`, { replace: true });
        return;
      }

      // If router requested a return URL, go there
      if (fromState) {
        navigate(fromState, { replace: true });
        return;
      }

      const ctx = getContext();
      const u = getCachedUser();
      const admin = isAdminUser(u);

      // Normal users MUST land on server dept
      if (!admin) {
        if (!ctx.department) {
          setErrorMsg(
            "Your account is missing a department assignment. Please contact the AMO Administrator or Quality/IT."
          );
          return;
        }
        navigate(`/maintenance/${slugToUse}/${ctx.department}`, { replace: true });
        return;
      }

      // Admin/superuser: use dropdown as landing preference (DO NOT override stored context)
      const landingDept = ctx.department || "admin";
      navigate(`/maintenance/${slugToUse}/${landingDept}`, { replace: true });
    } catch (err: unknown) {
      console.error("Login error:", err);
      if (err instanceof Error) {
        const msg = err.message.toLowerCase();
        if (msg.includes("locked")) {
          setErrorMsg(
            "Your account is locked due to repeated failed attempts. Please contact Quality or IT support."
          );
        } else if (
          msg.includes("401") ||
          msg.includes("unauthorized") ||
          msg.includes("invalid credentials") ||
          msg.includes("incorrect")
        ) {
          setErrorMsg("Invalid email or password.");
        } else if (msg.includes("not found") || msg.includes("amo")) {
          setErrorMsg(
            "AMO not found. Check the AMO portal link or contact support."
          );
        } else {
          setErrorMsg("Could not sign in. Please try again.");
        }
      } else {
        setErrorMsg("Could not sign in. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const amoSlugForLabel = loginContext?.login_slug || amoCode || null;

  const humanAmoLabel = loginContext?.amo_name
    ? loginContext.amo_name
    : amoSlugForLabel
      ? decodeAmoCertFromUrl(amoSlugForLabel)
      : "AMO";

  const isPlatformLogin = !!loginContext?.is_platform;

  const title = loginContext
    ? isPlatformLogin
      ? "Platform sign in"
      : `AMO sign in (${humanAmoLabel})`
    : "Find your sign-in";

  const subtitle = loginContext
    ? isPlatformLogin
      ? "Superusers only. Use your platform credentials."
      : `Use your AMO work email and password for ${humanAmoLabel}.`
    : "Enter your work email and we will route you to the right portal.";

  return (
    <AuthLayout title={title} subtitle={subtitle}>
      <form
        className="auth-form"
        onSubmit={step === "identify" ? handleIdentify : handleSubmit}
        noValidate
      >
        {errorMsg && <div className="auth-form__error">{errorMsg}</div>}

        <TextField
          label="Work email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          name="email"
          required
          disabled={step === "password"}
        />

        {step === "password" && (
          <TextField
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            name="password"
            required
          />
        )}

        <div className="auth-form__field">
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

        {step === "password" && !amoCode && (
          <button
            type="button"
            className="auth-form__link"
            onClick={resetContext}
            disabled={loading}
          >
            Use a different email
          </button>
        )}

        <p className="auth-form__smallprint">
          Access is logged. Use only your personal account.
        </p>

        <div className="auth-form__actions">
          {step === "identify" ? (
            <Button
              type="submit"
              loading={loadingContext}
              disabled={loadingContext}
            >
              {loadingContext ? "Checking..." : "Continue"}
            </Button>
          ) : (
            <Button type="submit" loading={loading} disabled={loading}>
              {loading ? "Signing in..." : "Sign in"}
            </Button>
          )}
        </div>
      </form>
    </AuthLayout>
  );
};

export default LoginPage;
