import React, { useState } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import { createOverride, listOverrides } from "../../services/esign";
import type { PolicyOverride } from "../../types/esign";
import ESignModuleGate from "./ESignModuleGate";

const ESignOverridesPage: React.FC = () => {
  const { requestId = "" } = useParams();
  const [rows, setRows] = useState<PolicyOverride[]>([]);
  const [overrideType, setOverrideType] = useState("ALLOW_FALLBACK");
  const [justification, setJustification] = useState("");
  const [confirm, setConfirm] = useState(false);

  const refresh = async () => {
    setRows(await listOverrides(requestId));
  };

  const submit = async () => {
    if (!confirm || !justification.trim()) return;
    await createOverride(requestId, { override_type: overrideType, justification });
    setJustification("");
    setConfirm(false);
    await refresh();
  };

  return (
    <ESignModuleGate>
      <PageHeader title="Policy Overrides" subtitle="Admin-only exceptional controls. Overrides never relabel achieved assurance." />
      <SectionCard title="Create override">
        <select value={overrideType} onChange={(e) => setOverrideType(e.target.value)}>
          <option value="ALLOW_FALLBACK">ALLOW_FALLBACK</option>
          <option value="BYPASS_PROVIDER_HEALTHCHECK">BYPASS_PROVIDER_HEALTHCHECK</option>
          <option value="ACCEPT_NO_TIMESTAMP">ACCEPT_NO_TIMESTAMP</option>
        </select>
        <textarea placeholder="Justification" value={justification} onChange={(e) => setJustification(e.target.value)} />
        <label>
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
          I confirm this override is exceptional and auditable.
        </label>
        <div className="esign-actions">
          <button type="button" onClick={() => void submit()}>Create override</button>
          <button type="button" onClick={() => void refresh()}>Refresh list</button>
        </div>
      </SectionCard>
      <SectionCard title="Existing overrides">
        <pre>{JSON.stringify(rows, null, 2)}</pre>
      </SectionCard>
    </ESignModuleGate>
  );
};

export default ESignOverridesPage;
