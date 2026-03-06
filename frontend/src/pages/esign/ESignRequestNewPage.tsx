import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import { createRequest, sendRequest } from "../../services/esign";
import ESignModuleGate from "./ESignModuleGate";

const ESignRequestNewPage: React.FC = () => {
  const navigate = useNavigate();
  const { amoCode = "", department = "quality" } = useParams();
  const [title, setTitle] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [sourceRef, setSourceRef] = useState("");
  const [policyCode, setPolicyCode] = useState("");
  const [signerUserId, setSignerUserId] = useState("");
  const [x, setX] = useState("120");
  const [y, setY] = useState("90");
  const [message, setMessage] = useState<string | null>(null);

  const handleCreate = async (sendNow: boolean) => {
    try {
      const created = await createRequest({
        title,
        document_id: documentId,
        source_storage_ref: sourceRef,
        policy_code: policyCode || null,
        signers: [{ signer_type: "INTERNAL_USER", user_id: signerUserId || null, display_name: "Internal signer" }],
        field_placements: [{ page: 1, x: Number(x), y: Number(y) }],
      });
      if (sendNow) {
        await sendRequest(created.request_id);
      }
      navigate(`/maintenance/${amoCode}/${department}/esign/requests/${created.request_id}`);
    } catch (error) {
      const text = error instanceof Error ? error.message : "Failed to create request";
      setMessage(text);
    }
  };

  return (
    <ESignModuleGate>
      <PageHeader title="New Signature Request" subtitle="Phase 3 reuses backend create/send with explicit policy visibility." />
      <SectionCard title="Request form" subtitle="Appearance-only is not cryptographic signing; policy may require crypto provider.">
        <div className="esign-form-grid">
          <input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <input placeholder="Document ID" value={documentId} onChange={(e) => setDocumentId(e.target.value)} />
          <input placeholder="Source storage ref (server path)" value={sourceRef} onChange={(e) => setSourceRef(e.target.value)} />
          <input placeholder="Policy code (optional)" value={policyCode} onChange={(e) => setPolicyCode(e.target.value)} />
          <input placeholder="Internal signer user id" value={signerUserId} onChange={(e) => setSignerUserId(e.target.value)} />
          <input placeholder="Signature X" value={x} onChange={(e) => setX(e.target.value)} />
          <input placeholder="Signature Y" value={y} onChange={(e) => setY(e.target.value)} />
        </div>
        {message && <p className="inline-error">{message}</p>}
        <div className="esign-actions">
          <button type="button" onClick={() => void handleCreate(false)}>Create draft</button>
          <button type="button" onClick={() => void handleCreate(true)}>Create and send</button>
        </div>
      </SectionCard>
    </ESignModuleGate>
  );
};

export default ESignRequestNewPage;
