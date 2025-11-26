// src/pages/LoginPage.tsx
import React, { useEffect, useState } from "react";
import { useNavigate, useLocation, useParams } from "react-router-dom";
import AuthLayout from "../components/Layout/AuthLayout";
import TextField from "../components/UI/TextField";
import Button from "../components/UI/Button";
import { login, setContext, getToken } from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Optional default AMO slug for /login (no AMO in URL)
const DEFAULT_AMO_CODE: string | null =
  import.meta.env.VITE_DEFAULT_AMO_CODE || null;

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

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { amoCode } = useParams<{ amoCode?: string }>();

  const [email, setEmail] = useState(
    import.meta.env.DEV ? "admin@amo.local" : ""
  );
  const [password, setPassword] = useState(
    import.meta.env.DEV ? "ChangeMe123!" : ""
  );
  const [department, setDepartment] = useState<string>("planning");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const fromState = (location.state as { from?: string } | null)?.from;

  // If already logged in, bounce straight to the dashboard
  useEffect(() => {
    const token = getToken();
    if (!token) return;

    const effectiveAmoCode = amoCode ?? DEFAULT_AMO_CODE;
    if (!effectiveAmoCode) return;

    const target =
      fromState || `/maintenance/${effectiveAmoCode}/${department}`;
    navigate(target, { replace: true });
  }, [navigate, fromState, amoCode, department]);

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

    const effectiveAmoCode = amoCode ?? DEFAULT_AMO_CODE;
    if (!effectiveAmoCode) {
      console.error("Login attempted without any AMO code configured.");
      setErrorMsg(
        "Configuration error: AMO code is missing. Please use your AMO-specific portal link or contact the system administrator."
      );
      return;
    }

    try {
      setLoading(true);

      // IMPORTANT: backend now expects amo_slug + email + password.
      // We treat department as a landing page only, not as part of auth.
      await login(effectiveAmoCode, trimmedEmail, password);

      // Remember AMO + preferred landing department for routing
      setContext(effectiveAmoCode, department);

      navigate(`/maintenance/${effectiveAmoCode}/${department}`, {
        replace: true,
      });
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

  const amoSlugForLabel = amoCode ?? DEFAULT_AMO_CODE;
  const humanAmoLabel = amoSlugForLabel
    ? decodeAmoCertFromUrl(amoSlugForLabel)
    : "AMO";

  const title = amoSlugForLabel
    ? `Sign in to AMO Portal (${humanAmoLabel})`
    : "Sign in to AMO Portal";

  const subtitle = amoSlugForLabel
    ? `Use your personal Safarilink AMO credentials for ${humanAmoLabel}.`
    : "Use your personal Safarilink AMO credentials.";

  const amoUrlHint = amoSlugForLabel
    ? `/maintenance/${amoSlugForLabel}/login`
    : null;

  return (
    <AuthLayout title={title} subtitle={subtitle}>
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        {errorMsg && <div className="auth-form__error">{errorMsg}</div>}

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
            Landing department (does not affect permissions)
          </label>
          <select
            className="auth-form__select"
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
          >
            {DEPARTMENTS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </div>

        {amoUrlHint && (
          <div className="auth-form__hint">
            AMO URL:&nbsp;
            <code>{amoUrlHint}</code>
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
