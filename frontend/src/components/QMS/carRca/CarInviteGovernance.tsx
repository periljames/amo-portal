import { useCallback, useEffect, useState } from "react";
import {
  getCarInviteAccessControl, updateCarInviteAccessControl, rotateCarInviteAccess,
  type CarInviteAccessControl,
} from "../../../services/qmsCarRca";
import { formatInviteExpiryLocal, parseInviteExpiryLocal } from "../../../utils/carInviteExpiry";
import "./car-rca.css";

export default function CarInviteGovernance({ amoCode, carId, canManage, onChanged }: {
  amoCode: string; carId: string; canManage: boolean; onChanged?: () => void;
}) {
  const [control, setControl] = useState<CarInviteAccessControl | null>(null);
  const [expiry, setExpiry] = useState("");
  const [reason, setReason] = useState("");
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [newUrl, setNewUrl] = useState("");
  const showControl = useCallback((row: CarInviteAccessControl) => {
    setControl(row);
    setExpiry(formatInviteExpiryLocal(row.expires_at));
  }, []);
  useEffect(() => {
    let mounted = true;
    setError(null); setControl(null); setNewUrl("");
    void getCarInviteAccessControl(amoCode, carId).then(row => {
      if (!mounted) return;
      showControl(row);
    }).catch(e => { if (mounted) setError(e instanceof Error ? e.message : "Invitation controls unavailable"); });
    return () => { mounted = false; };
  }, [amoCode, carId, showControl]);
  const apply = async (revoke: boolean) => {
    if (!canManage || busy || reason.trim().length < 8 || (revoke && !confirmRevoke)) return;
    setBusy(true); setError(null); setMessage(null); setNewUrl("");
    try {
      const expires_at = parseInviteExpiryLocal(expiry, control?.expires_at ?? null);
      const next = await updateCarInviteAccessControl(amoCode, carId, { revoke, expires_at, reason: reason.trim() });
      showControl(next); setConfirmRevoke(false); setReason("");
      setMessage(revoke ? "This invitation has been revoked. The old link will no longer work." : "The controlled invitation expiry has been updated.");
      onChanged?.();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not change invitation controls."); }
    finally { setBusy(false); }
  };
  const rotate = async () => {
    if (!canManage || busy || reason.trim().length < 8 || !confirmRevoke) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const next = await rotateCarInviteAccess(amoCode, carId, reason.trim());
      showControl(next); setReason(""); setConfirmRevoke(false);
      setNewUrl(next.new_invite_url);
      setMessage("A replacement invitation is ready. The previous bearer token is invalid.");
      onChanged?.();
    } catch(e) { setError(e instanceof Error ? e.message : "Could not rotate invitation."); }
    finally { setBusy(false); }
  };
  return <section className="card car-rca" aria-label="CAR invitation security">
    <div className="car-rca-heading"><div><h3>Invitation access and security</h3>
      <p>Public CAR links are bearer capabilities. Only Quality may set expiry, revoke access, or rotate a link. Previously issued links remain valid until explicitly limited.</p>
    </div></div>
    {error && <p role="alert">{error} <button type="button" onClick={() => void getCarInviteAccessControl(amoCode,carId).then(row => { showControl(row); setError(null); }).catch(e => setError(String(e)))}>Retry</button></p>}
    {!control && !error && <p role="status">Loading invitation controls…</p>}
    {control && <div className="car-rca-analysis">
      <p><strong>Access status:</strong> {control.revoked_at ? "Revoked" :
        control.expires_at && new Date(control.expires_at).getTime() <= Date.now() ? "Expired" :
          control.expires_at ? "Time-limited" : "Active (no scheduled expiry)"}</p>
      {control.revoked_at && <p>Revoked: {new Date(control.revoked_at).toLocaleString()}</p>}
      {control.reason && <p>Last decision: {control.reason}</p>}
      {message && <p role="status">{message}</p>}
      {newUrl && <div className="car-rca-row"><input readOnly aria-label="Replacement CAR invitation" value={newUrl} />
        <button type="button" onClick={() => void navigator.clipboard.writeText(newUrl).then(() => setMessage("Replacement invitation copied."), () => setError("Browser clipboard access was denied. Select and copy the URL manually."))}>Copy replacement link</button>
      </div>}
      {canManage && <div className="car-rca-analysis">
        {!control.revoked_at && <label className="car-rca-field">Optional expiry (local date and time)
          <input type="datetime-local" disabled={busy} value={expiry} onChange={e => setExpiry(e.target.value)} />
        </label>}
        <label className="car-rca-field">Mandatory controlled change reason
          <textarea rows={2} maxLength={4000} disabled={busy} value={reason}
            onChange={e => setReason(e.target.value)} placeholder="State why access must be changed or replaced."/>
        </label>
        <label className="car-rca-check"><input type="checkbox" checked={confirmRevoke} onChange={e => setConfirmRevoke(e.target.checked)} disabled={busy} />
          I confirm that revoking or rotating will immediately invalidate the previous link.
        </label>
        <div className="car-rca-row">
          {!control.revoked_at && <button type="button" disabled={busy || reason.trim().length < 8} onClick={() => void apply(false)}>
            Save expiry</button>}
          {!control.revoked_at && <button type="button" disabled={busy || !confirmRevoke || reason.trim().length < 8}
            onClick={() => void apply(true)}>Revoke current link</button>}
          <button type="button" disabled={busy || !confirmRevoke || reason.trim().length < 8}
            onClick={() => void rotate()}>Issue replacement link</button>
        </div>
      </div>}
    </div>}
  </section>;
}
