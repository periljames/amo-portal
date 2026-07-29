import { useEffect, useState } from "react";

import {
  messagingApi,
  type TenantEmailPreferences,
} from "../../services/messaging";

const DEFAULTS: TenantEmailPreferences = {
  routine_email_enabled: false,
  receipt_email_enabled: false,
  marketing_email_enabled: false,
  mandatory_email_classes: ["ESSENTIAL", "CRITICAL"],
};

export default function TenantEmailPreferencesPanel() {
  const [value, setValue] = useState<TenantEmailPreferences>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    messagingApi.tenantPreferences()
      .then(setValue)
      .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)))
      .finally(() => setLoading(false));
  }, []);

  const toggle = (key: keyof TenantEmailPreferences, checked: boolean) => {
    setValue((current) => ({ ...current, [key]: checked }));
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const next = await messagingApi.updateTenantPreferences({
        routine_email_enabled: value.routine_email_enabled,
        receipt_email_enabled: value.receipt_email_enabled,
        marketing_email_enabled: value.marketing_email_enabled,
      });
      setValue(next);
      setNotice("Tenant email delivery preferences saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="saas-admin__panel">
      <div className="saas-admin__panel-heading">
        <div>
          <p className="saas-admin__eyebrow">Tenant communications</p>
          <h2>Email delivery preferences</h2>
          <p>Choose optional email classes. Account security and critical compliance escalation remain active as portal features.</p>
        </div>
      </div>
      {loading ? <p>Loading email preferences…</p> : (
        <div className="saas-admin__form">
          <div className="saas-admin__alert saas-admin__alert--success">
            <strong>Always active:</strong> password recovery, account security, overdue compliance actions and critical escalation.
          </div>
          <label><input type="checkbox" checked={value.routine_email_enabled} onChange={(event) => toggle("routine_email_enabled", event.target.checked)} /> Routine operational email</label>
          <label><input type="checkbox" checked={value.receipt_email_enabled} onChange={(event) => toggle("receipt_email_enabled", event.target.checked)} /> Delivery and workflow receipts</label>
          <label><input type="checkbox" checked={value.marketing_email_enabled} onChange={(event) => toggle("marketing_email_enabled", event.target.checked)} /> Product updates, surveys and promotional communication</label>
          {error ? <div className="saas-admin__alert saas-admin__alert--error">{error}</div> : null}
          {notice ? <div className="saas-admin__alert saas-admin__alert--success">{notice}</div> : null}
          <button type="button" onClick={() => void save()} disabled={saving}>{saving ? "Saving…" : "Save email preferences"}</button>
        </div>
      )}
    </section>
  );
}
