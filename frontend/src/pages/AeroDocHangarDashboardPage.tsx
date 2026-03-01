import { useEffect, useMemo, useState } from "react";
import { fetchEntitlements } from "../services/billing";
import { apiGet } from "../services/crs";
import { authHeaders } from "../services/auth";

type VerifyResponse = { serial: string; status: string; current: boolean; approved_version?: string | null };

const MODULE_KEY = "aerodoc_hybrid_dms";

export default function AeroDocHangarDashboardPage() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [serial, setSerial] = useState("");
  const [result, setResult] = useState<VerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchEntitlements()
      .then((rows) => {
        const entitlement = rows.find((row) => row.key === MODULE_KEY);
        setEnabled(Boolean(entitlement && (entitlement.is_unlimited || (entitlement.limit ?? 0) > 0)));
      })
      .catch(() => setEnabled(false));
  }, []);

  const statusClass = useMemo(() => (result?.status === "GREEN" ? "ok" : "bad"), [result?.status]);

  const verify = async () => {
    setError(null);
    setResult(null);
    try {
      const data = await apiGet<VerifyResponse>(`/quality/qms/physical-copies/verify/${encodeURIComponent(serial.trim())}`, {
        headers: authHeaders(),
      });
      setResult(data);
      if (data.status === "RED" && typeof navigator !== "undefined" && "vibrate" in navigator) {
        navigator.vibrate?.([120, 80, 120]);
      }
    } catch (err: any) {
      setError(err?.message || "Verification failed");
    }
  };

  if (enabled === false) {
    return <section className="panel"><h2>Module not enabled</h2><p>AeroDoc Hybrid-DMS is not enabled for this tenant.</p></section>;
  }

  return (
    <section className="panel">
      <h2>Hangar Dashboard</h2>
      <p>Offline-ready verification of controlled copy QR serials.</p>
      <div style={{ display: "flex", gap: 8 }}>
        <input value={serial} onChange={(e) => setSerial(e.target.value)} placeholder="Enter QR serial" />
        <button type="button" onClick={verify} disabled={!serial.trim()}>Verify</button>
      </div>
      {error ? <p style={{ color: "var(--danger, #d9534f)" }}>{error}</p> : null}
      {result ? (
        <div style={{ marginTop: 12, border: "1px solid var(--border-color, #555)", padding: 12 }} className={statusClass === "bad" ? "danger" : "success"}>
          <strong>Status: {result.status}</strong>
          <p>Current: {result.current ? "Yes" : "No"}</p>
          <p>Approved version: {result.approved_version || "N/A"}</p>
        </div>
      ) : null}
    </section>
  );
}
