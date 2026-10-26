import { useEffect, useRef, useState, type ButtonHTMLAttributes } from "react";
import { AlertCircle, CheckCircle2, LoaderCircle, Save, Volume2, VolumeX, X } from "lucide-react";
import "./qms-settings.css";
import { getNotificationPreferences, NOTIFICATION_PREFS_EVENT, playNotificationCue, prepareNotificationAudio, setNotificationPreferences } from "../../services/notificationPreferences";

export function SettingsSoundControl() {
  const [enabled, setEnabled] = useState(() => getNotificationPreferences().audioEnabled);
  useEffect(() => {
    prepareNotificationAudio();
    const sync = () => setEnabled(getNotificationPreferences().audioEnabled);
    window.addEventListener(NOTIFICATION_PREFS_EVENT, sync);
    return () => window.removeEventListener(NOTIFICATION_PREFS_EVENT, sync);
  }, []);
  return <button type="button" className="qms-settings__sound" aria-label="Notification sounds" aria-pressed={enabled} title="Notification sounds on this device" onClick={() => { setNotificationPreferences({ audioEnabled: !enabled }); if (!enabled) playNotificationCue("success"); }}>
    {enabled ? <Volume2 size={17} /> : <VolumeX size={17} />}<span>Sound {enabled ? "on" : "off"}</span>
  </button>;
}

export function SettingsFeedback({ message, error = false, onDismiss, children }: { message: string; error?: boolean; onDismiss?: () => void; children?: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!message) return;
    if (error) { ref.current?.focus({ preventScroll: true }); ref.current?.scrollIntoView({ block: "nearest" }); }
    else playNotificationCue("success");
  }, [message, error]);
  if (!message) return null;
  return <div ref={ref} tabIndex={error ? -1 : undefined} role={error ? "alert" : "status"} aria-atomic="true" data-portal-error-feedback={error ? "true" : undefined} className={`qms-settings__feedback ${error ? "qms-settings__error" : "qms-settings__success"}`}>
    {error ? <AlertCircle size={20} /> : <CheckCircle2 size={20} />}<div><strong>{error ? "Change needs attention" : "Saved successfully"}</strong><p>{message}</p>{children}</div>
    {onDismiss && <button type="button" className="qms-settings__dismiss" aria-label={error ? "Dismiss error" : "Dismiss confirmation"} onClick={onDismiss}><X size={17} /></button>}
  </div>;
}

export function SettingsSaveButton({ busy, saved, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { busy: boolean; saved?: boolean }) {
  return <button {...props} className={`qms-settings__primary ${props.className || ""}`} aria-busy={busy} data-state={busy ? "saving" : saved ? "saved" : "idle"}>
    {busy ? <LoaderCircle size={17} className="qms-settings__spinner" /> : saved ? <CheckCircle2 size={17} /> : <Save size={17} />}<span>{children}</span>
  </button>;
}
