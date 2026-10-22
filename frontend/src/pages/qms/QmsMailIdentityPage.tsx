import InlineLoading from "../../components/shared/InlineLoading";
import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CheckCircle2, CircleAlert, ExternalLink, MailCheck, RefreshCw, Send, ShieldCheck } from "lucide-react";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { qmsMailIdentityApi, type QmsMailIdentity, type QmsMailIdentityUpdate, type QmsMailTestResult } from "../../services/qmsMailIdentity";
import "./qmsMailIdentity.css";

type SenderChoice = "SHARED" | "CUSTOM";
type ReplyChoice = "QUALITY_ROLES" | "CUSTOM";

const initialReason = "QMS mailing identity configuration approved by Quality management";

export default function QmsMailIdentityPage(): React.ReactElement {
  const { amoCode = "" } = useParams<{ amoCode: string }>();
  const [settings, setSettings] = useState<QmsMailIdentity | null>(null);
  const [draft, setDraft] = useState<QmsMailIdentityUpdate>({
    from_name: "", from_email: "", reply_to: "", enabled: true, reason: initialReason,
  });
  const [senderChoice, setSenderChoice] = useState<SenderChoice>("SHARED");
  const [replyChoice, setReplyChoice] = useState<ReplyChoice>("QUALITY_ROLES");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [testResult, setTestResult] = useState<QmsMailTestResult | null>(null);

  const apply = useCallback((data: QmsMailIdentity) => {
    setSettings(data);
    setDraft({
      from_name: data.from_name,
      from_email: data.sender_mode === "CUSTOM" ? data.from_email : "",
      reply_to: data.reply_to,
      enabled: data.enabled,
      reason: initialReason,
    });
    setSenderChoice(data.sender_mode);
    setReplyChoice(data.reply_mode);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      apply(await qmsMailIdentityApi.get(amoCode));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [amoCode, apply]);

  useEffect(() => { void load(); }, [load]);

  const visibleFrom = senderChoice === "SHARED" ? (settings?.shared_sender || "") : draft.from_email;
  const domain = draft.from_email.includes("@") ? draft.from_email.split("@").pop()?.toLowerCase() || "" : "";
  const customApproved = senderChoice !== "CUSTOM" || (settings?.custom_domains.includes(domain) ?? false);
  const canSave = Boolean(
    settings?.can_manage && !loading && !busy && draft.from_name.trim().length >= 2
    && draft.reason.trim().length >= 8 && visibleFrom
    && customApproved && (senderChoice !== "CUSTOM" || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.from_email))
  );

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSave) return;
    setBusy("save");
    setError("");
    setNotice("");
    setTestResult(null);
    try {
      const result = await qmsMailIdentityApi.save(amoCode, {
        ...draft,
        from_email: senderChoice === "SHARED" ? "" : draft.from_email.trim(),
        reply_to: replyChoice === "QUALITY_ROLES" ? "" : draft.reply_to.trim(),
      });
      apply(result);
      setNotice("QMS sender identity saved. Venspera continues to manage Resend credentials and verified domains.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(null);
    }
  };

  const sendTest = async () => {
    if (!settings?.can_manage || busy) return;
    setBusy("test");
    setError("");
    setNotice("");
    setTestResult(null);
    try {
      const result = await qmsMailIdentityApi.test(amoCode);
      setTestResult(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(null);
    }
  };

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <main className="qms-mail" aria-labelledby="qms-mail-title">
        <header className="qms-mail__header">
          <div>
            <p className="qms-mail__eyebrow">Quality Management System / Administration</p>
            <h1 id="qms-mail-title">Notification mailing identity</h1>
            <p>Set the sender used for audit notices and other tenant QMS notifications. Resend transport and domain approval remain under Venspera.</p>
          </div>
          <button type="button" onClick={() => void load()} disabled={loading || Boolean(busy)}><RefreshCw size={16} /> Refresh</button>
        </header>

        {error && <div className="qms-mail__message qms-mail__message--error" role="alert">{error}</div>}
        {notice && <div className="qms-mail__message" role="status">{notice}</div>}
        {loading && <p><InlineLoading label={"Loading the tenant's current mail configuration…"}/></p>}

        {settings && !loading && (
          <>
            <div className="qms-mail__summary">
              <div><span>Tenant</span><strong>{settings.tenant_name}</strong></div>
              <div><span>Resend transport</span><strong>{settings.provider_status.replaceAll("_", " ")}</strong></div>
              <div><span>Sending mode</span><strong>{settings.sending_mode}</strong></div>
              <div><span>Identity</span><strong>{settings.enabled ? "Enabled" : "Suspended"}</strong></div>
            </div>
            {!settings.ready && (
              <div className="qms-mail__message qms-mail__message--warning" role="status">
                <CircleAlert size={18} />
                <div>Mail is not currently delivery-ready. Venspera must verify the sending domain, configure Resend, and enable the appropriate sending mode. Saving this page does not activate transport.</div>
              </div>
            )}
            {!settings.can_manage && <div className="qms-mail__message qms-mail__message--warning">Only your Quality Manager or tenant Administrator may change mailing settings.</div>}

            <div className="qms-mail__grid">
              <form className="qms-mail__card" onSubmit={(event) => void save(event)}>
                <div className="qms-mail__card-heading"><MailCheck size={20} /><div><h2>Sending identity</h2><p>Each tenant uses its own identity without access to Venspera's API credentials.</p></div></div>
                <label className="qms-mail__field"><span>Display name</span>
                  <input value={draft.from_name} onChange={(e) => setDraft(v => ({ ...v, from_name: e.target.value }))} maxLength={150} disabled={!settings.can_manage || Boolean(busy)} required />
                </label>
                <fieldset className="qms-mail__field">
                  <legend>Sender address</legend>
                  <label className="qms-mail__choice">
                    <input type="radio" name="sender" value="SHARED" checked={senderChoice === "SHARED"} disabled={!settings.can_manage || Boolean(busy)} onChange={() => setSenderChoice("SHARED")} />
                    <span>Venspera-managed tenant address <small>{settings.shared_sender || "Platform domain not configured"}</small></span>
                  </label>
                  <label className="qms-mail__choice">
                    <input type="radio" name="sender" value="CUSTOM" checked={senderChoice === "CUSTOM"} disabled={!settings.can_manage || Boolean(busy) || !settings.custom_domains.length} onChange={() => setSenderChoice("CUSTOM")} />
                    <span>Tenant-owned verified domain <small>Requires prior Venspera approval and assignment</small></span>
                  </label>
                  {senderChoice === "CUSTOM" && (
                    <label className="qms-mail__field"><span>Approved custom sender</span>
                      <input type="email" value={draft.from_email} onChange={(e) => setDraft(v => ({ ...v, from_email: e.target.value }))} placeholder="quality@yourdomain.com" disabled={!settings.can_manage || Boolean(busy)} required />
                      <small>Domains available to this tenant: {settings.custom_domains.join(", ") || "None. Contact Venspera to verify and assign one."}</small>
                      {!customApproved && <small className="qms-mail__field-error">This domain is not assigned to this tenant.</small>}
                    </label>
                  )}
                </fieldset>
                <fieldset className="qms-mail__field">
                  <legend>Reply handling</legend>
                  <label className="qms-mail__choice"><input type="radio" name="reply" checked={replyChoice === "QUALITY_ROLES"} onChange={() => setReplyChoice("QUALITY_ROLES")} disabled={!settings.can_manage || Boolean(busy)} />
                    <span>Active Quality Manager and Quality Officers <small>Automatically follows staff changes in this tenant</small></span>
                  </label>
                  <label className="qms-mail__choice"><input type="radio" name="reply" checked={replyChoice === "CUSTOM"} onChange={() => setReplyChoice("CUSTOM")} disabled={!settings.can_manage || Boolean(busy)} />
                    <span>Specified reply mailbox(es) <small>Use comma or semicolon to separate mailboxes</small></span>
                  </label>
                  {replyChoice === "CUSTOM" && <label className="qms-mail__field"><span>Reply-To destinations</span>
                    <textarea value={draft.reply_to} onChange={(e) => setDraft(v => ({ ...v, reply_to: e.target.value }))} rows={2} disabled={!settings.can_manage || Boolean(busy)} placeholder="quality@yourdomain.com" required />
                  </label>}
                </fieldset>
                <label className="qms-mail__choice"><input type="checkbox" checked={draft.enabled} onChange={(e) => setDraft(v => ({ ...v, enabled: e.target.checked }))} disabled={!settings.can_manage || Boolean(busy)} />
                  <span>Enable tenant QMS email sending <small>Uncheck to block outbound tenant email instead of falling back to Venspera's sender.</small></span>
                </label>
                <label className="qms-mail__field"><span>Configuration change reason</span>
                  <textarea rows={2} minLength={8} maxLength={500} required value={draft.reason} onChange={(e) => setDraft(v => ({ ...v, reason: e.target.value }))} disabled={!settings.can_manage || Boolean(busy)} />
                </label>
                <div className="qms-mail__actions"><button className="qms-mail__primary" type="submit" disabled={!canSave}>{busy === "save" ? "Saving…" : "Save mailing identity"}</button></div>
              </form>

              <aside className="qms-mail__side">
                <section className="qms-mail__card">
                  <div className="qms-mail__card-heading"><ShieldCheck size={20}/><div><h2>Message preview</h2><p>Headers that recipients will see in normal production delivery.</p></div></div>
                  <dl className="qms-mail__preview">
                    <div><dt>From</dt><dd>{draft.from_name || "Quality"} &lt;{visibleFrom || "Not configured"}&gt;</dd></div>
                    <div><dt>Reply-To</dt><dd>{replyChoice === "CUSTOM" ? (draft.reply_to || "Not configured") : (settings.effective_reply_to || "No active Quality accounts found")}</dd></div>
                    <div><dt>Audit CC</dt><dd>Assigned auditor and designated audit CC participants, subject to sandbox redirection</dd></div>
                  </dl>
                  <p className="qms-mail__footnote">For audits, AMO Portal includes the assigned audit team and CC contacts in reply routing. Email clients ultimately control Reply versus Reply All.</p>
                </section>
                <section className="qms-mail__card">
                  <div className="qms-mail__card-heading"><Send size={20}/><div><h2>Test and verification</h2><p>Send one controlled test to your account email (or configured sandbox destinations).</p></div></div>
                  <button type="button" onClick={() => void sendTest()} disabled={!settings.can_manage || Boolean(busy) || !settings.enabled || !settings.ready}>{busy === "test" ? "Submitting…" : "Send test to my account"}</button>
                  {testResult && <div className="qms-mail__test-result" role="status">
                    <strong>{testResult.delivery_status === "ACCEPTED" ? "Accepted by Resend" : testResult.delivery_status.replaceAll("_", " ")}</strong>
                    <small>Log: {testResult.email_log_id}</small>
                    {testResult.provider_message_id && <small>Resend message: {testResult.provider_message_id}</small>}
                    <p>{testResult.detail}</p>
                  </div>}
                  <p className="qms-mail__footnote"><CheckCircle2 size={15}/> Verified webhooks are required before reporting recipient-server delivery. Open tracking is not proof of human reading; inbox versus junk cannot be inferred.</p>
                  <a href="https://resend.com/domains" target="_blank" rel="noreferrer">Resend domain verification <ExternalLink size={14}/></a>
                </section>
                <section className="qms-mail__card">
                  <h2>Governance</h2>
                  <p>Only Venspera assigns custom sender domains. Tenant Quality management controls its sender name, approved address, and Reply-To. Provider API keys never leave platform administration.</p>
                  <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/settings`}>Back to QMS settings</Link>
                </section>
              </aside>
            </div>
          </>
        )}
      </main>
    </DepartmentLayout>
  );
}
