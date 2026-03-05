import React, { useEffect, useState } from "react";
import PageHeader from "../components/shared/PageHeader";
import SectionCard from "../components/shared/SectionCard";
import InlineLoader from "../components/loading/InlineLoader";
import SectionLoader from "../components/loading/SectionLoader";
import { useAsyncWithLoader } from "../hooks/useAsyncWithLoader";
import {
  beginRegistration,
  completeRegistration,
  listWebAuthnCredentials,
  removeWebAuthnCredential,
  renameWebAuthnCredential,
} from "../services/esign";
import type { WebAuthnCredential } from "../types/esign";
import { createCredential, isSecureContextAvailable, isWebAuthnSupported } from "../lib/webauthn";
import ESignModuleGate from "./esign/ESignModuleGate";
import { buildPasskeyLabel, validatePasskeyNickname } from "./esign/passkeyManagementState";

const formatDate = (value: string | null) => (value ? new Date(value).toLocaleString() : "Never");

const AccountSecurityPage: React.FC = () => {
  const withLoader = useAsyncWithLoader();
  const [items, setItems] = useState<WebAuthnCredential[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const supported = isWebAuthnSupported();
  const secure = isSecureContextAvailable();

  const load = async () => {
    setLoading(true);
    try {
      const rows = await withLoader(() => listWebAuthnCredentials(), {
        scope: "account-security",
        label: "Loading passkeys",
        phase: "loading",
        mode_preference: "section",
      });
      setItems(rows);
      setStatus("");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to load passkeys");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!supported) {
      setLoading(false);
      setStatus("Passkeys are not supported in this browser.");
      return;
    }
    if (!secure) {
      setLoading(false);
      setStatus("Passkeys require a secure connection (HTTPS).");
      return;
    }
    void load();
  }, []);

  const addPasskey = async () => {
    if (!supported || !secure) return;
    setBusyAction("add");
    try {
      await withLoader(
        async () => {
          setStatus("Preparing passkey setup…");
          const options = await beginRegistration();
          setStatus("Confirm on your device…");
          const credential = await createCredential(options);
          if (!credential) {
            setStatus("Passkey setup cancelled.");
            return;
          }
          await completeRegistration(credential);
          setStatus("Passkey added.");
          const refreshed = await listWebAuthnCredentials();
          setItems(refreshed);
        },
        {
          scope: "account-security",
          label: "Preparing passkey setup",
          phase: "initializing",
          message: "Preparing passkey setup",
          allow_overlay: true,
          mode_preference: "auto",
        }
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Passkey setup failed";
      if (message.toLowerCase().includes("abort") || message.toLowerCase().includes("cancel")) {
        setStatus("Passkey setup cancelled.");
      } else {
        setStatus(message);
      }
    } finally {
      setBusyAction(null);
    }
  };

  const beginRename = (item: WebAuthnCredential) => {
    setRenameId(item.id);
    setRenameValue(item.nickname || "");
  };

  const saveRename = async () => {
    if (!renameId) return;
    const validation = validatePasskeyNickname(renameValue);
    if (!validation.ok) {
      setStatus(validation.error || "Invalid nickname");
      return;
    }
    setBusyAction(`rename-${renameId}`);
    try {
      await withLoader(
        async () => {
          await renameWebAuthnCredential(renameId, validation.normalized ?? null);
          const refreshed = await listWebAuthnCredentials();
          setItems(refreshed);
          setRenameId(null);
          setRenameValue("");
          setStatus("Passkey renamed.");
        },
        {
          scope: "account-security",
          label: "Renaming passkey",
          phase: "validating",
          mode_preference: "inline",
        }
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to rename passkey");
    } finally {
      setBusyAction(null);
    }
  };

  const removeCredential = async (credentialId: string) => {
    if (!window.confirm("Remove this passkey from your account?")) return;
    setBusyAction(credentialId);
    try {
      await withLoader(
        async () => {
          await removeWebAuthnCredential(credentialId);
          const refreshed = await listWebAuthnCredentials();
          setItems(refreshed);
          setStatus("Passkey removed.");
        },
        {
          scope: "account-security",
          label: "Removing passkey",
          phase: "validating",
          mode_preference: "inline",
        }
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to remove passkey");
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <ESignModuleGate>
      <PageHeader title="Account Settings · Security" subtitle="Use passkeys to approve signing actions on this device." />
      {loading ? <SectionLoader title="Loading passkeys" message="Checking your passkey registrations" phase="loading" /> : null}
      <SectionCard title="Passkeys">
        <p>Use a passkey to approve signing and login actions on this device.</p>
        <button type="button" onClick={() => void addPasskey()} disabled={!!busyAction || !supported || !secure}>
          {busyAction === "add" ? <InlineLoader label="Adding passkey" /> : "Add passkey"}
        </button>
        {status && <p>{status}</p>}
        <ul className="loader-passkey-list">
          {items.map((item) => (
            <li key={item.id}>
              <div>
                <strong>{buildPasskeyLabel(item)}</strong>
                <div>ID: {item.credential_id_masked}</div>
                <div>Created: {formatDate(item.created_at)}</div>
                <div>Last used: {formatDate(item.last_used_at)}</div>
                <div>Transport: {(item.transports || []).join(", ") || "Not reported"}</div>
              </div>
              <div className="loader-passkey-actions">
                {renameId === item.id ? (
                  <>
                    <input
                      aria-label="Passkey nickname"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      maxLength={50}
                    />
                    <button type="button" onClick={() => void saveRename()} disabled={!!busyAction}>
                      {busyAction === `rename-${item.id}` ? <InlineLoader label="Saving" /> : "Save"}
                    </button>
                    <button type="button" onClick={() => { setRenameId(null); setRenameValue(""); }} disabled={!!busyAction}>Cancel</button>
                  </>
                ) : (
                  <button type="button" onClick={() => beginRename(item)} disabled={!!busyAction}>Rename</button>
                )}
                <button type="button" onClick={() => void removeCredential(item.id)} disabled={!!busyAction}>
                  {busyAction === item.id ? <InlineLoader label="Removing" /> : "Remove"}
                </button>
              </div>
            </li>
          ))}
          {!items.length && !loading && <li>No passkeys registered.</li>}
        </ul>
      </SectionCard>
    </ESignModuleGate>
  );
};

export default AccountSecurityPage;
