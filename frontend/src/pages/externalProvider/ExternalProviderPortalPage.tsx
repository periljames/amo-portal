import React, { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { getApiBaseUrl } from "../../services/config";
import {
  createCredential, decodeCreationOptions, decodeRequestOptions,
  getAssertion, isSecureContextAvailable, isWebAuthnSupported,
  serializeRegistrationCredential, serializeAssertionCredential,
} from "../../lib/webauthn";
import "./external-provider-portal.css";

type Account = {
  csrf: string; identity_id: string; amo_id: string; supplier_id: number;
  role: string; portal_state: string; capabilities: string[];
  restricted: boolean; mfa_verified: boolean;
};
type Member = { id: string; email: string; display_name: string; role_code: string; status: string };
type Session = { id: string; created_at: string; last_seen_at: string | null; expires_at: string; revoked_at: string | null };
const BASE = "/api/external-provider";
class VendorHttpError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "VendorHttpError";
    this.status = status;
  }
}
const roles = [
  "PROVIDER_ADMIN", "QUALITY_REPRESENTATIVE", "TECHNICAL_REPRESENTATIVE",
  "COMMERCIAL_REPRESENTATIVE", "DOCUMENT_SUBMITTER", "READ_ONLY",
];
const labelRole = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (x) => x.toUpperCase());
const pathFor = (page: string) => `/vendor/${page}`;
async function vendorFetch<T>(path: string, data?: object, csrf?: string, method = "POST"): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${BASE}${path}`, {
    method: data === undefined ? "GET" : method,
    credentials: "include",
    headers: {
      ...(data !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(csrf ? { "X-External-CSRF": csrf } : {}),
    },
    ...(data !== undefined ? { body: JSON.stringify(data) } : {}),
    cache: "no-store",
  });
  const body = await response.json().catch(() => ({})) as { detail?: string } & T;
  if (!response.ok) {
    throw new VendorHttpError(response.status,
      typeof body.detail === "string" ? body.detail : `Request rejected (${response.status})`);
  }
  return body;
}

const Field: React.FC<{
  title: string; type?: string; value: string; onChange: (v: string) => void;
  required?: boolean; autoComplete?: string;
}> = ({ title, type = "text", value, onChange, required, autoComplete }) => (
  <label className="vendor-field"><span>{title}</span>
    <input aria-label={title} type={type} value={value} required={required}
      autoComplete={autoComplete} onChange={(event) => onChange(event.target.value)} />
  </label>
);
export default function ExternalProviderPortalPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const mode = location.pathname.split("/")[2] || "login";
  const [account, setAccount] = useState<Account | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [amoSlug, setAmoSlug] = useState("");
  const [vendorKey, setVendorKey] = useState("");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [code, setCode] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [totpSeed, setTotpSeed] = useState("");
  const [members, setMembers] = useState<Member[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSession, setCurrentSession] = useState("");
  const [passkeys, setPasskeys] = useState<Array<{id: string;nickname: string;created_at:string}>>([]);
  const [newRole, setNewRole] = useState("READ_ONLY");
  const [profileName, setProfileName] = useState("");

  const reload = useCallback(async () => {
    try {
      const session = await vendorFetch<Account>("/session");
      setAccount(session);
      return session;
    } catch (reason) {
      setAccount(null);
      if (mode === "account" && reason instanceof VendorHttpError) {
        if (reason.status === 403) navigate(pathFor("denied"), { replace: true });
        else if (reason.status === 401) navigate(pathFor("revoked"), { replace: true });
      }
      return null;
    } finally { setLoading(false); }
  }, [mode, navigate]);
  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => {
    if (mode !== "account" || !account) return;
    if (account.capabilities.includes("members.read")) {
      void vendorFetch<{ items: Member[] }>("/members").then((value) => setMembers(value.items)).catch(() => setMembers([]));
    }
    if (account.capabilities.includes("sessions.manage")) {
      void vendorFetch<{ items: Session[]; current_session_id: string }>("/sessions")
        .then((value) => { setSessions(value.items); setCurrentSession(value.current_session_id); })
        .catch(() => setSessions([]));
    }
  }, [account?.identity_id, mode, account?.role]);

  async function perform(action: () => Promise<unknown>, success: string, logout = false) {
    setBusy(true); setError(""); setNotice("");
    try {
      await action();
      setNotice(success);
      setPassword(""); setNewPassword(""); setCode(""); setTotpCode("");
      if (logout) { setAccount(null); navigate(pathFor("login")); }
      else await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to complete action.");
    } finally { setBusy(false); }
  }

  const refreshPasskeys = useCallback(async () => {
    const result = await vendorFetch<{items:Array<{id:string;nickname:string;created_at:string}>}>("/passkeys");
    setPasskeys(result.items);
  }, []);
  useEffect(() => {
    if (mode === "account" && account) {
      void refreshPasskeys().catch(() => setPasskeys([]));
    }
  }, [mode, account?.identity_id, refreshPasskeys]);

  const registerPasskey = () => {
    if (!account || !isSecureContextAvailable() || !isWebAuthnSupported()) {
      setError("Passkeys require a secure HTTPS browser context.");
      return;
    }
    void perform(async () => {
      const start = await vendorFetch<{challenge_id:string;options:Record<string,unknown>}>(
        "/passkeys/register/options", { password }, account.csrf);
      const credential = await createCredential(decodeCreationOptions(start.options));
      if (!credential) throw new Error("Passkey registration cancelled");
      await vendorFetch("/passkeys/register/verify", {
        challenge_id: start.challenge_id, credential: serializeRegistrationCredential(credential),
      }, account.csrf);
      await refreshPasskeys();
    }, "Passkey registered. It can now verify sensitive account actions.");
  };
  const verifyPasskey = () => {
    if (!account || !isSecureContextAvailable() || !isWebAuthnSupported()) {
      setError("Passkeys require a secure HTTPS browser context.");
      return;
    }
    void perform(async () => {
      const start = await vendorFetch<{challenge_id:string;options:Record<string,unknown>}>(
        "/passkeys/challenge/options", {}, account.csrf);
      const credential = await getAssertion(decodeRequestOptions(start.options));
      if (!credential) throw new Error("Passkey verification cancelled");
      await vendorFetch("/passkeys/challenge/verify", {
        challenge_id: start.challenge_id, credential: serializeAssertionCredential(credential),
      }, account.csrf);
    }, "Passkey verified for this session.");
  };

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode === "login") {
      void perform(async () => {
        const result = await vendorFetch<{ csrf: string }>("/login", {
          amo_slug: amoSlug.trim(), vendor_key: vendorKey.trim() || null,
          email: email.trim(), password, totp_code: totpCode.trim() || null,
        });
        setAccount((old) => old ? { ...old, csrf: result.csrf } : null);
        navigate(`/partner/${encodeURIComponent(amoSlug.trim())}/home`);
      }, "Signed in.");
    } else if (mode === "invite") {
      void perform(() => vendorFetch("/invitations/accept", {
        code, password: newPassword || null, display_name: name || null,
      }), "Email verified. Your tenant administrator must activate your access.", true);
    } else if (mode === "forgot") {
      void perform(() => vendorFetch("/password/forgot", { amo_slug: amoSlug, email }),
        "If the account exists, a recovery code will be sent.");
    } else if (mode === "reset") {
      void perform(() => vendorFetch("/password/reset", { code, password: newPassword }),
        "Password changed. Sign in with your new credentials.", true);
    } else if (mode === "verify") {
      void perform(() => vendorFetch("/verification/confirm", { code }),
        "Email verified. Quality must approve reactivation.", true);
    }
  };
  if (loading) return <main className="vendor-portal" role="status">Loading vendor access…</main>;
  const authenticated = Boolean(account);
  const showForm = ["login", "invite", "forgot", "reset", "verify"].includes(mode);
  return <main className="vendor-portal">
    <div className="vendor-shell">
      <header className="vendor-header">
        <div><span className="vendor-eyebrow">AMO PORTAL · EXTERNAL PROVIDERS</span>
          <h1>Vendor access</h1>
          <p>Managed access to assigned work only. Vendor keys identify organizations, not passwords.</p>
        </div>
        <nav aria-label="Vendor account navigation">
          {authenticated ? <>
            <Link to={pathFor("account")}>Account</Link>
            <button type="button" disabled={busy} onClick={() => void perform(
              () => vendorFetch("/logout", {}, account!.csrf), "Signed out.", true,
            )}>Sign out</button>
          </> : <Link to={pathFor("login")}>Sign in</Link>}
        </nav>
      </header>
      {error ? <div role="alert" className="vendor-error">{error}</div> : null}
      {notice ? <div role="status" className="vendor-success">{notice}</div> : null}
      {showForm && <section className="vendor-card vendor-auth" aria-label="External provider authentication">
        <h2>{mode === "login" ? "Sign in" : mode === "invite" ? "Accept invitation" :
          mode === "forgot" ? "Recover account" : mode === "verify" ? "Verify your account" : "Reset password"}</h2>
        <form onSubmit={submit}>
          {["login", "forgot"].includes(mode) && <>
            <Field title="AMO tenant code" value={amoSlug} onChange={setAmoSlug} required />
            <Field title="Email address" type="email" value={email} onChange={setEmail} required autoComplete="email" />
          </>}
          {mode === "login" && <>
            <Field title="Vendor key (optional if unique)" value={vendorKey} onChange={setVendorKey} />
            <Field title="Password" type="password" value={password} onChange={setPassword} required autoComplete="current-password" />
            <Field title="MFA code (when enrolled)" value={totpCode} onChange={setTotpCode} />
          </>}
          {["invite", "reset", "verify"].includes(mode) && <Field title="One-time email code" value={code} onChange={setCode} required />}
          {["invite", "reset"].includes(mode) && <Field title="New password (invited existing users may leave blank)" type="password" value={newPassword} onChange={setNewPassword} autoComplete="new-password" required={mode === "reset"} />}
          <button className="vendor-primary" type="submit" disabled={busy}>{busy ? "Processing…" :
            mode === "login" ? "Secure sign in" : mode === "invite" ? "Accept invitation" :
              mode === "forgot" ? "Send recovery code" : mode === "verify" ? "Verify" : "Reset password"}</button>
        </form>
        <div className="vendor-links">
          <Link to={pathFor("invite")}>Invitation</Link>
          <Link to={pathFor("forgot")}>Forgot password</Link>
          <Link to={pathFor("reset")}>Enter recovery code</Link>
          <Link to={pathFor("verify")}>Re-verification</Link>
        </div>
      </section>}
      {["denied","revoked"].includes(mode) && !authenticated && <section className="vendor-card vendor-auth" role="alert">
        <h2>{mode === "denied" ? "Provider access denied" : "Provider session unavailable"}</h2>
        <p>{mode === "denied"
          ? "Your tenant or provider has restricted this operation. Contact the Quality Department for an authorized access review."
          : "Your session has expired, ended or been revoked. Sign in again to verify current account privileges."}</p>
        <p><Link to={pathFor("login")}>Return to secure vendor login</Link></p>
      </section>}
      {mode === "account" && !authenticated && <section className="vendor-card" role="alert">
        Your session has ended or access has been revoked. <Link to={pathFor("login")}>Sign in again</Link>.
      </section>}
      {mode === "account" && account && <>
        <section className="vendor-card">
          <h2>My external account</h2>
          <dl className="vendor-facts">
            <div><dt>Provider</dt><dd>{account.supplier_id}</dd></div>
            <div><dt>Role</dt><dd>{labelRole(account.role)}</dd></div>
            <div><dt>Tenant access</dt><dd>{account.portal_state}</dd></div>
            <div><dt>New work</dt><dd>{account.restricted ? "Restricted" : "As assigned"}</dd></div>
          </dl>
          <form onSubmit={(event) => {
            event.preventDefault();
            void perform(() => vendorFetch("/profile", { display_name: profileName }, account.csrf, "PATCH"),
              "Profile name updated.");
          }} className="vendor-profile-form">
            <Field title="Update profile display name" value={profileName} onChange={setProfileName} required />
            <button type="submit" disabled={busy || profileName.trim().length < 2}>Save profile</button>
          </form>
          <h3>Granted capabilities</h3>
          <p>{account.capabilities.map(labelRole).join(" · ")}</p>
          <p>Record, contract and document access is additionally restricted by the assignments granted by your AMO.</p>
        </section>
        <div className="vendor-columns">
          <section className="vendor-card">
            <h2>Password and security</h2>
            <form onSubmit={(event) => {
              event.preventDefault();
              void perform(() => vendorFetch("/password/change", {
                current_password: password, new_password: newPassword, totp_code: totpCode || null,
              }, account.csrf), "Password changed. Sign in again.", true);
            }}>
              <Field title="Current password" type="password" value={password} onChange={setPassword} required />
              <Field title="New password" type="password" value={newPassword} onChange={setNewPassword} required />
              <Field title="Current MFA code (if enabled)" value={totpCode} onChange={setTotpCode} />
              <button type="submit" disabled={busy}>Change password and revoke sessions</button>
            </form>
            <h3>Authenticator MFA</h3>
            {!totpSeed && <button type="button" disabled={busy} onClick={() => void perform(async () => {
              const value = await vendorFetch<{ secret: string }>("/mfa/enroll", { password }, account.csrf);
              setTotpSeed(value.secret);
            }, "Enter the secret in your authenticator, then verify the six-digit code.")}>Start MFA enrollment</button>}
            <div className="vendor-actions">
              <Field title="MFA challenge code" value={totpCode} onChange={setTotpCode} />
              <button type="button" disabled={busy || totpCode.length !== 6} onClick={() => void perform(
                () => vendorFetch("/mfa/challenge", { code: totpCode }, account.csrf),
                "Second factor re-verified for sensitive actions.",
              )}>Reverify MFA</button>
            </div>
            <h3>Passkey security</h3>
            <p>Registered passkeys: {passkeys.length}. Registration requires your current password and an HTTPS browser.</p>
            <div className="vendor-actions">
              <button type="button" disabled={busy || !isWebAuthnSupported()} onClick={registerPasskey}>Register passkey</button>
              <button type="button" disabled={busy || passkeys.length === 0} onClick={verifyPasskey}>Verify with passkey</button>
            </div>
            <p>Passkey verification authorizes sensitive actions for a limited time. Password login remains available.</p>
            {totpSeed && <div>
              <p>Authenticator setup secret (shown once): <code>{totpSeed}</code></p>
              <Field title="Authenticator 6-digit code" value={totpCode} onChange={setTotpCode} />
              <button type="button" disabled={busy} onClick={() => void perform(
                async () => {
                  await vendorFetch("/mfa/verify", { code: totpCode }, account.csrf);
                  setTotpSeed("");
                },
                "MFA verified and active.",
              )}>Verify and activate MFA</button>
            </div>}
          </section>
          <section className="vendor-card">
            <h2>Active sessions</h2>
            <button type="button" onClick={() => void perform(async () => {
              const items = await vendorFetch<{ items: Session[]; current_session_id: string }>("/sessions");
              setSessions(items.items); setCurrentSession(items.current_session_id);
            }, "Sessions refreshed.")}>Refresh sessions</button>
            <ul className="vendor-list">{sessions.map((session) => <li key={session.id}>
              <div><strong>{session.id === currentSession ? "This session" : "Other session"}</strong>
                <small>Created {new Date(session.created_at).toLocaleString()}</small>
                <small>{session.revoked_at ? "Revoked" : `Expires ${new Date(session.expires_at).toLocaleString()}`}</small>
              </div>
              {!session.revoked_at && <button type="button" disabled={busy} onClick={() => void perform(
                () => vendorFetch(`/sessions/revoke/${encodeURIComponent(session.id)}`, {}, account.csrf),
                "Session revoked.", session.id === currentSession,
              )}>Revoke</button>}
            </li>)}</ul>
            <button type="button" disabled={busy} onClick={() => void perform(
              () => vendorFetch("/logout-all", {}, account.csrf),
              "All sessions revoked.", true,
            )}>Sign out from every device</button>
          </section>
        </div>
        {account.capabilities.includes("members.read") && <section className="vendor-card">
          <h2>Organization members</h2>
          <ul className="vendor-list">{members.map((member) => <li key={member.id}>
            <div><strong>{member.display_name}</strong><small>{member.email}</small></div>
            <span>{labelRole(member.role_code)} · {member.status}</span>
            {account.capabilities.includes("members.manage") && member.status !== "REVOKED" &&
              <button disabled={busy} onClick={() => void perform(
                () => vendorFetch(`/members/${encodeURIComponent(member.id)}/revoke`, {}, account.csrf),
                "Member access revoked. All of their sessions for this provider are invalidated.",
              )}>Revoke access</button>}
          </li>)}</ul>
          {account.capabilities.includes("members.manage") && <form onSubmit={(event) => {
            event.preventDefault();
            void perform(() => vendorFetch("/members/invite", {
              email, name, role_code: newRole, object_scope: {},
            }, account.csrf), "Invitation issued for Quality approval.");
          }} className="vendor-invite">
            <h3>Invite a member</h3>
            <Field title="Member email" type="email" value={email} onChange={setEmail} required />
            <Field title="Member full name" value={name} onChange={setName} required />
            <label className="vendor-field"><span>Requested external role</span>
              <select value={newRole} onChange={(event) => setNewRole(event.target.value)}>
                {roles.map((role) => <option value={role} key={role}>{labelRole(role)}</option>)}
              </select>
            </label>
            <button type="submit" disabled={busy}>Request member invitation</button>
            <small>New members remain pending until the tenant Quality Manager approves their access.</small>
          </form>}
        </section>}
      </>}
    </div>
  </main>;
}
