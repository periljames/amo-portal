// src/pages/PasswordResetPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import AuthLayout from "../components/Layout/AuthLayout";
import TextField from "../components/UI/TextField";
import Button from "../components/UI/Button";
import {
  confirmPasswordReset,
  getLoginContext,
  getPasswordResetChannels,
  requestPasswordReset,
  type PasswordResetDeliveryMethod,
} from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";

const PasswordResetPage: React.FC = () => {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const token = (params.get("token") || "").trim();
  const amoSlug = (params.get("amo") || "").trim();

  const [email, setEmail] = useState(params.get("email") || "");
  const [deliveryMethod, setDeliveryMethod] =
    useState<PasswordResetDeliveryMethod>("email");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [channels, setChannels] = useState({email:false, whatsapp:false});
  const [channelsLoading, setChannelsLoading] = useState(true);
  useEffect(() => {
    if (token) { setChannelsLoading(false); return; }
    let active = true;
    getPasswordResetChannels().then(value => { if(active) {setChannels(value); if(!value.email && value.whatsapp) setDeliveryMethod("whatsapp");} })
      .catch(() => { if(active) setErrorMsg("Recovery options could not be loaded. Please try again shortly."); })
      .finally(() => { if(active) setChannelsLoading(false); });
    return () => {active=false;};
  }, [token]);

  const isConfirmMode = useMemo(() => !!token, [token]);

  const handleRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!email.trim()) {
      setErrorMsg("Please enter your work email address.");
      return;
    }

    try {
      setLoading(true);
      let slugToUse = amoSlug;

      if (!slugToUse) {
        const context = await getLoginContext(email.trim());
        slugToUse = context.login_slug;
      }

      const response = await requestPasswordReset(
        slugToUse || "system",
        email,
        deliveryMethod
      );
      setSuccessMsg(response.message);
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

  const handleBackToLogin = () => {
    const target = amoSlug ? `/maintenance/${amoSlug}/login` : "/login";
    navigate(target, { replace: true });
  };

  const brandName = amoSlug ? decodeAmoCertFromUrl(amoSlug) : null;

  return (
    <AuthLayout
      title={isConfirmMode ? "Reset your password" : "Forgot your password?"}
      subtitle={
        isConfirmMode
          ? "Create a new secure password to regain access."
          : "Enter your work email to receive a reset link."
      }
      brandName={brandName}
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

            <div className="auth-form__field">
              {channels.whatsapp ? <><label htmlFor="deliveryMethod">Send reset link via</label>
                <select id="deliveryMethod" value={deliveryMethod} onChange={e=>setDeliveryMethod(e.target.value as PasswordResetDeliveryMethod)}>
                  {channels.email ? <option value="email">Email</option> : null}<option value="whatsapp">WhatsApp (phone on file)</option>
                  {channels.email ? <option value="both">Email + WhatsApp</option> : null}
                </select></> : <div className="auth-form__hint">{channelsLoading ? "Checking recovery options..." : channels.email ? "We will email the reset link to your registered address. WhatsApp recovery is not currently available." : "Password recovery is unavailable. Please contact your administrator."}</div>}
              {successMsg ? <div className="auth-form__hint">Check your inbox and junk folder.</div> : null}
            </div>
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
          <Button type="submit" disabled={loading || (!isConfirmMode && (channelsLoading || (!channels.email && !channels.whatsapp)))}>
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
