// src/pages/LoginPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useLocation, useParams } from "react-router-dom";
import AuthLayout from "../components/Layout/AuthLayout";
import TextField from "../components/UI/TextField";
import Button from "../components/UI/Button";
import { login, getToken, getCachedUser, getContext } from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Optional default AMO slug for /login (no AMO in URL)
const DEFAULT_AMO_CODE: string | null =
  import.meta.env.VITE_DEFAULT_AMO_CODE || null;

// Platform support slug (superuser login)
const PLATFORM_SUPPORT_SLUG = "root";

const DEPARTMENTS = [
  { value: "planning", label: "Planning" },
  { value: "production", label: "Production" },
  { value: "quality", label: "Quality & Compliance" },
  { value: "safety", label: "Safety Management" },
  { value: "stores", label: "Procurement & Stores" },
  { value: "engineering", label: "Engineering" },
  { value: "workshops", label: "Workshops" },
  { value: "admin", label: "System Admin" },
];

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

  // Admin landing preference ONLY (normal users ignore)
  const [department, setDepartment] = useState<string>("planning");
  const [supportMode, setSupportMode] = useState<boolean>(false);

  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const fromState = (location.state as { from?: string } | null)?.from;

  const effectiveAmoSlug = useMemo(() => {
    if (supportMode) return PLATFORM_SUPPORT_SLUG;
    return amoCode ?? DEFAULT_AMO_CODE ?? "";
  }, [supportMode, amoCode]);

  const canAttemptNormalLogin = useMemo(() => {
    if (supportMode) return true;
    return !!(amoCode ?? DEFAULT_AMO_CODE);
  }, [supportMode, amoCode]);

  // If already logged in, bounce straight to dashboard
  useEffect(() => {
    const token = getToken();
    if (!token) return;

    const slug = supportMode
      ? PLATFORM_SUPPORT_SLUG
      : (amoCode ?? DEFAULT_AMO_CODE);

    if (!slug) return;

    const ctx = getContext();
    const u = getCachedUser();
    const admin = isAdminUser(u);

    // If router gave us a "from" location, respect it
    if (fromState) {
      navigate(fromState, { replace: true });
      return;
    }

    // Normal users MUST go to server-assigned department
    const landingDept = admin ? (department || ctx.department || "admin") : (ctx.department || null);

    if (!admin && !landingDept) {
      // Stay on login and show a clean error
      setErrorMsg(
        "Your account is missing a department assignment. Please contact the AMO Administrator or Quality/IT."
      );
      return;
    }

    navigate(`/maintenance/${slug}/${landingDept}`, { replace: true });
  }, [navigate, fromState, amoCode, department, supportMode]);

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

    if (!canAttemptNormalLogin) {
      setErrorMsg(
        "AMO code is missing. Use your AMO-specific portal link, or enable platform support login."
      );
      return;
    }

    const slugToUse = effectiveAmoSlug.trim();
    if (!slugToUse) {
      setErrorMsg(
        "AMO code is missing. Use your AMO-specific portal link, or enable platform support login."
      );
      return;
    }

    try {
      setLoading(true);

      // login() stores:
      // - token
      // - server-provided AMO + department context
      // - cached user
      await login(slugToUse, trimmedEmail, password);

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
      const landingDept = (department || "").trim() || ctx.department || "admin";
      navigate(`/maintenance/${slugToUse}/${landingDept}`, { replace: true });
    } catch (err: unknown) {
      console.error("Login error:", err);
      if (err instanceof Error) {
        const msg = err.message.toLowerCase();
        if (msg.includes("locked")) {
          setErrorMsg(
            "Your account is locked due to repeated failed attempts. Please contact Quality or IT support."
          );
        } else if (msg.includes("401") || msg.includes("unauthorized")) {
          setErrorMsg("Invalid email or password.");
        } else if (msg.includes("not found") || msg.includes("amo")) {
          setErrorMsg(
            "AMO not found. Check the AMO portal link or disable support mode."
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

  const amoSlugForLabel = supportMode
    ? PLATFORM_SUPPORT_SLUG
    : (amoCode ?? DEFAULT_AMO_CODE);

  const humanAmoLabel = amoSlugForLabel
    ? decodeAmoCertFromUrl(amoSlugForLabel)
    : "AMO";

  const title = supportMode
    ? "Sign in (Platform Support)"
    : amoSlugForLabel
      ? `Sign in to AMO Portal (${humanAmoLabel})`
      : "Sign in to AMO Portal";

  const subtitle = supportMode
    ? "Use your platform superuser credentials. You can switch AMO context after login."
    : amoSlugForLabel
      ? `Use your personal Safarilink AMO credentials for ${humanAmoLabel}.`
      : "Use your personal Safarilink AMO credentials.";

  const amoUrlHint =
    !supportMode && amoSlugForLabel
      ? `/maintenance/${amoSlugForLabel}/login`
      : null;

  return (
    <AuthLayout title={title} subtitle={subtitle}>
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        {errorMsg && <div className="auth-form__error">{errorMsg}</div>}

        <div className="auth-form__field">
          <label className="auth-form__label">Login mode</label>
          <label style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={supportMode}
              onChange={(e) => setSupportMode(e.target.checked)}
              disabled={loading}
            />
            Platform support login (SUPERUSER)
          </label>
          {!supportMode && !amoCode && !DEFAULT_AMO_CODE && (
            <div className="auth-form__hint" style={{ marginTop: 6 }}>
              No AMO code detected. Enable support login or use an AMO-specific link.
            </div>
          )}
        </div>

        <TextField
          label="Work email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          name="email"
          required
        />

        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          name="password"
          required
        />

        <div className="auth-form__field">
          <label className="auth-form__label">
            Landing department (admins/superusers only)
          </label>
          <select
            className="auth-form__select"
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
            disabled={loading}
          >
            {DEPARTMENTS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
          <div className="auth-form__hint" style={{ marginTop: 6 }}>
            Normal users will be routed to their assigned department automatically.
          </div>
        </div>

        {amoUrlHint && (
          <div className="auth-form__hint">
            AMO URL:&nbsp;<code>{amoUrlHint}</code>
          </div>
        )}

        <p className="auth-form__smallprint">
          Use only your personal account. All access and actions are logged in
          line with AMO and authority requirements.
        </p>

        <div className="auth-form__actions">
          <Button type="submit" loading={loading} disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </Button>
        </div>
      </form>
    </AuthLayout>
  );
};

export default LoginPage;
