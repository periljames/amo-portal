// src/pages/PasswordResetPage.tsx
import React, { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import AuthLayout from "../components/Layout/AuthLayout";
import TextField from "../components/UI/TextField";
import Button from "../components/UI/Button";
import {
  confirmPasswordReset,
  requestPasswordReset,
  type PasswordResetResponse,
} from "../services/auth";

const PasswordResetPage: React.FC = () => {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const token = (params.get("token") || "").trim();
  const amoSlug = (params.get("amo") || "").trim();

  const [email, setEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [resetInfo, setResetInfo] = useState<PasswordResetResponse | null>(null);

  const isConfirmMode = useMemo(() => !!token, [token]);

  const handleRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);
    setResetInfo(null);

    if (!email.trim()) {
      setErrorMsg("Please enter your work email address.");
      return;
    }

    try {
      setLoading(true);
      const response = await requestPasswordReset(amoSlug || "root", email);
      setResetInfo(response);
      setSuccessMsg(
        "If the account exists, a password reset link has been prepared."
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Could not request reset.";
      setErrorMsg(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!newPassword || !confirmPassword) {
      setErrorMsg("Please enter and confirm your new password.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setErrorMsg("Passwords do not match.");
      return;
    }

    try {
      setLoading(true);
      await confirmPasswordReset(token, newPassword);
      setSuccessMsg("Your password has been reset. Please log in again.");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Could not reset password.";
      setErrorMsg(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyLink = async () => {
    if (!resetInfo?.reset_link) return;
    try {
      if (!navigator.clipboard) {
        throw new Error("Clipboard unavailable");
      }
      await navigator.clipboard.writeText(resetInfo.reset_link);
      setSuccessMsg("Reset link copied to clipboard.");
    } catch {
      setErrorMsg("Unable to copy reset link. Please copy it manually.");
    }
  };

  const handleBackToLogin = () => {
    const target = amoSlug ? `/maintenance/${amoSlug}/login` : "/login";
    navigate(target, { replace: true });
  };

  return (
    <AuthLayout
      title={isConfirmMode ? "Reset your password" : "Forgot your password?"}
      subtitle={
        isConfirmMode
          ? "Create a new secure password to regain access."
          : "Enter your work email to receive a reset link."
      }
    >
      <form className="auth-form" onSubmit={isConfirmMode ? handleConfirm : handleRequest}>
        {errorMsg && <div className="auth-form__error">{errorMsg}</div>}
        {successMsg && <div className="auth-form__success">{successMsg}</div>}

        {!isConfirmMode && (
          <>
            <TextField
              label="Work email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              name="email"
              required
            />

            {resetInfo?.reset_link && (
              <div className="auth-form__hint" style={{ marginBottom: 12 }}>
                Reset link (share via email/SSO):{" "}
                <code>{resetInfo.reset_link}</code>
              </div>
            )}
          </>
        )}

        {isConfirmMode && (
          <>
            <TextField
              label="New password"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              name="newPassword"
              required
            />
            <TextField
              label="Confirm new password"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              name="confirmPassword"
              required
            />
          </>
        )}

        <div className="auth-form__actions">
          {!isConfirmMode && resetInfo?.reset_link && (
            <Button type="button" className="btn-secondary" onClick={handleCopyLink}>
              Copy reset link
            </Button>
          )}

          <Button type="submit" disabled={loading}>
            {loading
              ? "Please wait..."
              : isConfirmMode
                ? "Reset password"
                : "Send reset link"}
          </Button>
        </div>

        <div className="auth-form__actions" style={{ marginTop: 12 }}>
          <Button type="button" className="btn-secondary" onClick={handleBackToLogin}>
            Back to login
          </Button>
        </div>
      </form>
    </AuthLayout>
  );
};

export default PasswordResetPage;
