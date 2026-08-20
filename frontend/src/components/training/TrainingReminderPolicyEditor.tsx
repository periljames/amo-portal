import React from "react";
import { BellRing } from "lucide-react";

type Props = {
  value: Record<string, unknown>;
  disabled?: boolean;
  onChange: (value: Record<string, unknown>) => void;
};

const objectValue = (value: unknown): Record<string, unknown> => (
  value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}
);

const listValue = (value: unknown): string[] => Array.isArray(value)
  ? value.map((item) => String(item).trim()).filter(Boolean)
  : [];

const positiveNumbers = (value: string): number[] => Array.from(new Set(
  value.split(",").map((item) => Number(item.trim())).filter((item) => Number.isInteger(item) && item > 0),
));

const positiveInteger = (value: string): number | undefined => {
  const parsed = Number(value);
  return value.trim() && Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
};

const TrainingReminderPolicyEditor: React.FC<Props> = ({ value, disabled = false, onChange }) => {
  const policy = objectValue(value);
  const reminders = objectValue(policy.compliance_reminders);
  const delivery = objectValue(policy.delivery);
  const channels = listValue(policy.external_channels).map((item) => item.toUpperCase());
  const patch = (next: Record<string, unknown>) => onChange({ ...policy, ...next });
  const patchReminders = (next: Record<string, unknown>) => patch({ compliance_reminders: { ...reminders, ...next } });
  const patchDelivery = (next: Record<string, unknown>) => patch({ delivery: { ...delivery, ...next } });
  const setChannel = (channel: string, selected: boolean) => patch({
    external_channels: selected
      ? Array.from(new Set([...channels, channel]))
      : channels.filter((item) => item !== channel),
  });

  return (
    <details className="tos-disclosure" id="notification-policy">
      <summary><span><BellRing size={18} /><strong>Notifications &amp; reminders</strong></span><small>Tenant-defined timing and provider delivery</small></summary>
      <div className="tos-disclosure__body">
        <p>No reminder day, retry count or external channel is supplied automatically. Enter the approved values for this tenant.</p>
        <div className="tos-form-grid">
          <label className="tos-check"><input type="checkbox" disabled={disabled} checked={reminders.enabled === true} onChange={(event) => patchReminders({ enabled: event.target.checked })} /><span>Enable compliance reminders</span></label>
          <label>Due reminder days<input disabled={disabled} value={listValue(reminders.due_days).join(", ")} onChange={(event) => patchReminders({ due_days: positiveNumbers(event.target.value) })} placeholder="Comma-separated days" /></label>
          <label>Overdue reminder days<input disabled={disabled} value={listValue(reminders.overdue_days).join(", ")} onChange={(event) => patchReminders({ overdue_days: positiveNumbers(event.target.value) })} placeholder="Comma-separated days" /></label>
          <label className="tos-check"><input type="checkbox" disabled={disabled} checked={channels.includes("EMAIL")} onChange={(event) => setChannel("EMAIL", event.target.checked)} /><span>Email</span></label>
          <label className="tos-check"><input type="checkbox" disabled={disabled} checked={channels.includes("WHATSAPP")} onChange={(event) => setChannel("WHATSAPP", event.target.checked)} /><span>WhatsApp</span></label>
          <label className="tos-check"><input type="checkbox" disabled={disabled} checked={delivery.enabled === true} onChange={(event) => patchDelivery({ enabled: event.target.checked })} /><span>Enable external delivery</span></label>
          <label>Channel strategy<select disabled={disabled} value={String(delivery.mode || "")} onChange={(event) => patchDelivery({ mode: event.target.value })}><option value="">Select</option><option value="FALLBACK">Fallback in channel order</option><option value="PARALLEL">Send all selected channels</option></select></label>
          <label>Attempts per channel<input type="number" min="1" max="20" disabled={disabled} value={delivery.max_attempts == null ? "" : String(delivery.max_attempts)} onChange={(event) => patchDelivery({ max_attempts: positiveInteger(event.target.value) })} /></label>
          <label>Retry base seconds<input type="number" min="1" disabled={disabled} value={delivery.retry_base_seconds == null ? "" : String(delivery.retry_base_seconds)} onChange={(event) => patchDelivery({ retry_base_seconds: positiveInteger(event.target.value) })} /></label>
          <label>Retry ceiling seconds<input type="number" min="1" disabled={disabled} value={delivery.retry_ceiling_seconds == null ? "" : String(delivery.retry_ceiling_seconds)} onChange={(event) => patchDelivery({ retry_ceiling_seconds: positiveInteger(event.target.value) })} /></label>
          <label className="tos-span-2">Escalation recipients<input disabled={disabled} value={listValue(delivery.escalation_user_ids).join(", ")} onChange={(event) => patchDelivery({ escalation_user_ids: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} placeholder="Comma-separated tenant user IDs" /><small>These users receive an in-app action when configured retries and fallbacks are exhausted.</small></label>
        </div>
      </div>
    </details>
  );
};

export default TrainingReminderPolicyEditor;
