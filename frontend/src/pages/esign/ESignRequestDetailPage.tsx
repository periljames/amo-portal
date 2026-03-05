import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import { createEvidenceBundle, fetchSigningContext } from "../../services/esign";
import { HashFingerprintBlock, PolicyBadge } from "../../components/esign/Badges";
import ESignModuleGate from "./ESignModuleGate";

const ESignRequestDetailPage: React.FC = () => {
  const { amoCode = "", department = "quality", requestId = "" } = useParams();
  const [contextMsg, setContextMsg] = useState("Load signing context to review signer intent and hash binding.");
  const [bundleId, setBundleId] = useState<string | null>(null);

  const loadContext = async () => {
    try {
      const context = await fetchSigningContext(requestId);
      setContextMsg(`Signer ${context.signer_id} viewing ${context.title}; doc hash ${context.doc_hash.slice(0, 12)}…`);
    } catch (error) {
      setContextMsg(error instanceof Error ? error.message : "Unable to load signing context");
    }
  };

  const generateBundle = async () => {
    try {
      const bundle = await createEvidenceBundle(requestId);
      setBundleId(bundle.bundle_id);
    } catch {
      setBundleId(null);
    }
  };

  return (
    <ESignModuleGate>
      <PageHeader
        title={`Request ${requestId}`}
        subtitle="Trust summary keeps approval, storage integrity, and cryptographic validation distinct."
        actions={<PolicyBadge level={null} />}
      />
      <SectionCard title="Operator actions">
        <p>{contextMsg}</p>
        <div className="esign-actions">
          <button type="button" onClick={() => void loadContext()}>Refresh signing context</button>
          <button type="button" onClick={() => void generateBundle()}>Generate evidence bundle</button>
          <Link to={`/maintenance/${amoCode}/${department}/esign/requests/${requestId}/evidence`}>Open evidence bundles</Link>
          <Link to={`/maintenance/${amoCode}/${department}/esign/requests/${requestId}/overrides`}>Manage overrides</Link>
        </div>
      </SectionCard>
      <SectionCard title="Assurance semantics">
        <p>WebAuthn approval records signer presence and intent. Appearance and cryptographic signature status are separate artifact properties.</p>
        <HashFingerprintBlock label="Document fingerprint" value="Load from signing context" />
      </SectionCard>
      {bundleId && (
        <SectionCard title="Evidence bundle generated">
          <p>Bundle id: {bundleId}</p>
        </SectionCard>
      )}
    </ESignModuleGate>
  );
};

export default ESignRequestDetailPage;
