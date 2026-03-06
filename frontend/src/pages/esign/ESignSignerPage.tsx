import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import InlineLoader from "../../components/loading/InlineLoader";
import SectionLoader from "../../components/loading/SectionLoader";
import { useGlobalLoading } from "../../hooks/useGlobalLoading";
import {
  beginRegistration,
  completeRegistration,
  listWebAuthnCredentials,
  startIntentAssertion,
  verifyIntentAssertion,
} from "../../services/esign";
import {
  createCredential,
  getAssertion,
  isSecureContextAvailable,
  isWebAuthnSupported,
} from "../../lib/webauthn";
import { getPasskeyEnvironmentMessage, getSignerPrimaryAction } from "./passkeyState";
import ESignModuleGate from "./ESignModuleGate";

const ESignSignerPage: React.FC = () => {
  const { intentId = "" } = useParams();
  const navigate = useNavigate();
  const { startLoading, updateLoading, stopLoading } = useGlobalLoading();
  const [status, setStatus] = useState("Checking passkey availability…");
  const [busy, setBusy] = useState(false);
  const [checkingCredentials, setCheckingCredentials] = useState(true);
  const [hasCredential, setHasCredential] = useState(false);
  const [preferredCredentialLabel, setPreferredCredentialLabel] = useState<string | null>(null);

  const supported = useMemo(() => isWebAuthnSupported(), []);
  const secure = useMemo(() => isSecureContextAvailable(), []);

  const refreshCredentialState = async () => {
    setCheckingCredentials(true);
    try {
      const rows = await listWebAuthnCredentials();
      const active = rows.filter((row) => row.is_active);
      setHasCredential(active.length > 0);
      setPreferredCredentialLabel(active.find((row) => row.nickname)?.nickname || null);
      setStatus(active.length > 0 ? "Ready to approve with your passkey." : "No passkey found. Set up a passkey to sign.");
    } catch (error) {
      setHasCredential(false);
      setStatus(error instanceof Error ? error.message : "Unable to load passkey status");
    } finally {
      setCheckingCredentials(false);
    }
  };

  useEffect(() => {
    const envMessage = getPasskeyEnvironmentMessage({ supported, secure });
    if (envMessage) {
      setStatus(envMessage);
      setCheckingCredentials(false);
      return;
    }
    void refreshCredentialState();
  }, [supported, secure]);

  const registerPasskey = async (): Promise<boolean> => {
    const taskId = startLoading({
      scope: "esign-signer",
      label: "Preparing passkey setup",
      phase: "initializing",
      message: "Preparing passkey setup",
      allow_overlay: true,
      mode_preference: "auto",
    });

    try {
      setStatus("Preparing passkey setup…");
      const options = await beginRegistration();
      updateLoading(taskId, { phase: "verifying", message: "Confirm on your device" });
      setStatus("Confirm passkey setup on your device…");
      const credential = await createCredential(options);
      if (!credential) {
        setStatus("Passkey setup cancelled.");
        return false;
      }
      updateLoading(taskId, { phase: "validating", message: "Verifying passkey registration" });
      await completeRegistration(credential);
      setStatus("Passkey added. Continuing to signing…");
      await refreshCredentialState();
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Passkey setup failed";
      if (message.toLowerCase().includes("abort") || message.toLowerCase().includes("cancel")) {
        setStatus("Passkey setup cancelled.");
      } else {
        setStatus(message);
      }
      return false;
    } finally {
      updateLoading(taskId, { phase: "completing", message: "Passkey setup complete" });
      stopLoading(taskId);
    }
  };

  const signWithPasskey = async () => {
    const taskId = startLoading({
      scope: "esign-signer",
      label: "Preparing signing session",
      phase: "initializing",
      message: "Preparing signing session",
      allow_overlay: true,
      mode_preference: "auto",
      priority: 90,
      minimum_visible_ms: 500,
    });

    try {
      setBusy(true);
      setStatus("Preparing signing session…");
      const options = await startIntentAssertion(intentId);
      updateLoading(taskId, { phase: "verifying", message: "Waiting for passkey approval" });

      setStatus("Waiting for passkey approval…");
      const credential = await getAssertion(options);
      if (!credential) {
        setStatus("Passkey approval cancelled.");
        updateLoading(taskId, { phase: "completing", message: "Signing cancelled" });
        return;
      }

      updateLoading(taskId, { phase: "validating", message: "Verifying signer approval" });
      const result = await verifyIntentAssertion(intentId, credential);
      updateLoading(taskId, { phase: "finalizing", message: "Finalizing signed artifact" });
      setStatus("Passkey approval recorded. Finalization complete.");
      navigate(`/verify/${result.verification_token}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Signing failed";
      if (message.toLowerCase().includes("abort") || message.toLowerCase().includes("cancel")) {
        setStatus("Passkey approval cancelled. You can try again.");
      } else {
        setStatus(message);
      }
    } finally {
      updateLoading(taskId, { phase: "completing", message: "Refreshing verification status" });
      stopLoading(taskId);
      setBusy(false);
    }
  };

  const primaryAction = async () => {
    if (!supported || !secure) return;
    if (hasCredential) {
      await signWithPasskey();
      return;
    }
    setBusy(true);
    const created = await registerPasskey();
    if (created) {
      await signWithPasskey();
    } else {
      setBusy(false);
    }
  };

  return (
    <ESignModuleGate>
      <PageHeader
        title="Signer Approval"
        subtitle="Passkey approval records signer intent. PDF cryptographic signature status depends on provider policy and finalization outcome."
      />
      {checkingCredentials ? <SectionLoader title="Checking passkey availability" message="Loading signer security context" phase="loading" /> : null}
      <SectionCard title="Sign with passkey">
        <p>{status}</p>
        {!supported && <p>Passkeys are not available in this browser.</p>}
        {supported && !secure && <p>Passkeys require a secure connection (HTTPS).</p>}
        <button type="button" onClick={() => void primaryAction()} disabled={busy || checkingCredentials || !supported || !secure}>
          {busy ? <InlineLoader label="Processing passkey flow" /> : (hasCredential && preferredCredentialLabel ? `Use passkey: ${preferredCredentialLabel}` : getSignerPrimaryAction(hasCredential))}
        </button>
      </SectionCard>
    </ESignModuleGate>
  );
};

export default ESignSignerPage;
