import { useEffect, useState } from "react";
import { fetchEntitlements } from "../services/billing";

const MODULE_KEY = "aerodoc_hybrid_dms";

export default function AeroDocComplianceHealthPage() {
  const [enabled, setEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    fetchEntitlements()
      .then((rows) => {
        const entitlement = rows.find((row) => row.key === MODULE_KEY);
        setEnabled(Boolean(entitlement && (entitlement.is_unlimited || (entitlement.limit ?? 0) > 0)));
      })
      .catch(() => setEnabled(false));
  }, []);

  if (enabled === false) return <section className="panel"><h2>Module not enabled</h2></section>;

  return (
    <section className="panel">
      <h2>Compliance Health Map</h2>
      <ul>
        <li>Unread manuals by department</li>
        <li>Pending approvals</li>
        <li>Controlled copy inventory by location</li>
      </ul>
    </section>
  );
}
