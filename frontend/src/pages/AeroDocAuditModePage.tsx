import { useEffect, useState } from "react";
import { fetchEntitlements } from "../services/billing";
import { authHeaders } from "../services/auth";

const MODULE_KEY = "aerodoc_hybrid_dms";

export default function AeroDocAuditModePage() {
  const [enabled, setEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    fetchEntitlements()
      .then((rows) => {
        const entitlement = rows.find((row) => row.key === MODULE_KEY);
        setEnabled(Boolean(entitlement && (entitlement.is_unlimited || (entitlement.limit ?? 0) > 0)));
      })
      .catch(() => setEnabled(false));
  }, []);

  const downloadBinder = async () => {
    const response = await fetch("/quality/qms/audit-mode/binder", { headers: authHeaders() });
    if (!response.ok) throw new Error("Failed to fetch binder");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "aerodoc-binder.zip";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (enabled === false) return <section className="panel"><h2>Module not enabled</h2></section>;

  return (
    <section className="panel">
      <h2>Inspector Audit Mode</h2>
      <p>Verify copies and export the compliance binder.</p>
      <button type="button" onClick={downloadBinder}>Download compliance binder</button>
    </section>
  );
}
