import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AuthLayout from "../components/Layout/AuthLayout";
import TextField from "../components/UI/TextField";
import Button from "../components/UI/Button";
import {
  changePassword,
  getCachedUser,
  getContext,
  logout,
} from "../services/auth";

const PASSWORD_MIN_LENGTH = 12;

function validatePassword(password: string, confirmPassword: string): string | null {
  if (!password || !confirmPassword) return "Please enter and confirm your new password.";
  if (password !== confirmPassword) return "Passwords do not match.";
  if (password.length < PASSWORD_MIN_LENGTH) {
    return `Password must be at least ${PASSWORD_MIN_LENGTH} characters.`;
  }

  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasDigit = /\d/.test(password);
  if (!hasUpper || !hasLower || !hasDigit) {
    return "Password must include uppercase, lowercase, and a number.";
  }

  return null;
}

const OnboardingPasswordPage: React.FC = () => {
  const navigate = useNavigate();
  const { amoCode } = useParams<{ amoCode?: string }>();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    const validationError = validatePassword(newPassword, confirmPassword);
    if (validationError) {
      setErrorMsg(validationError);
      return;
    }

    if (!currentPassword) {
      setErrorMsg("Please enter your current password.");
      return;
    }

    try {
      setLoading(true);
      await changePassword(currentPassword, newPassword);
      setSuccessMsg("Password updated. Redirecting to your dashboard...");

      const ctx = getContext();
      const user = getCachedUser();
      const isAdmin = !!user?.is_superuser || !!user?.is_amo_admin;
      const landing = isAdmin
        ? (ctx.department || "admin")
        : (ctx.department || null);

      if (!landing) {
        logout();
        navigate("/login", { replace: true });
        return;
      }

      const slug = amoCode || "root";
      navigate(`/maintenance/${slug}/${landing}`, { replace: true });
    } catch (err) {
      console.error("Password change failed", err);
      const message = err instanceof Error ? err.message : "Could not change password.";
      setErrorMsg(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Update your password"
      subtitle="Welcome! For security, please replace the default password before continuing."
    >
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        {errorMsg && <div className="auth-form__error">{errorMsg}</div>}
        {successMsg && <div className="auth-form__success">{successMsg}</div>}

        <TextField
          label="Current password"
          type="password"
          autoComplete="current-password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          name="currentPassword"
          required
        />

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

        <div className="auth-form__actions">
          <Button type="submit" disabled={loading}>
            {loading ? "Updating..." : "Update password"}
          </Button>
        </div>
      </form>
    </AuthLayout>
  );
};

export default OnboardingPasswordPage;
