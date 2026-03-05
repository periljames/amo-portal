import React, { useState } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import InlineLoader from "../../components/loading/InlineLoader";
import SectionLoader from "../../components/loading/SectionLoader";
import { useAsyncWithLoader } from "../../hooks/useAsyncWithLoader";
import { createEvidenceBundle, getEvidenceBundle, getEvidenceDownloadUrl } from "../../services/esign";
import ESignModuleGate from "./ESignModuleGate";

const ESignEvidencePage: React.FC = () => {
  const { requestId = "" } = useParams();
  const withLoader = useAsyncWithLoader();
  const [bundleId, setBundleId] = useState("");
  const [status, setStatus] = useState("No bundle loaded.");
  const [busy, setBusy] = useState<string | null>(null);

  const generate = async () => {
    try {
      setBusy("generate");
      const row = await withLoader(() => createEvidenceBundle(requestId), {
        scope: "esign-evidence",
        label: "Generating evidence bundle",
        phase: "generating",
        mode_preference: "section",
        allow_overlay: true,
      });
      setBundleId(row.bundle_id);
      setStatus(`Generated ${row.bundle_id}`);
    } finally {
      setBusy(null);
    }
  };

  const lookup = async () => {
    try {
      setBusy("lookup");
      const row = await withLoader(() => getEvidenceBundle(bundleId), {
        scope: "esign-evidence",
        label: "Loading evidence bundle metadata",
        phase: "loading",
        mode_preference: "inline",
      });
      setStatus(`Bundle ${row.bundle_id} hash ${row.bundle_sha256.slice(0, 16)}…`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <ESignModuleGate>
      <PageHeader title="Evidence Bundles" subtitle="Sanitized exports exclude secret tokens/challenges/provider credentials." />
      {busy === "generate" ? <SectionLoader title="Generating evidence bundle" message="Preparing sanitized export package" phase="generating" /> : null}
      <SectionCard title="Generate bundle">
        <button type="button" onClick={() => void generate()} disabled={!!busy}>
          {busy === "generate" ? <InlineLoader label="Generating" /> : "Generate now"}
        </button>
      </SectionCard>
      <SectionCard title="Lookup / download">
        <input value={bundleId} onChange={(e) => setBundleId(e.target.value)} placeholder="Bundle id" />
        <div className="esign-actions">
          <button type="button" onClick={() => void lookup()} disabled={!!busy || !bundleId.trim()}>
            {busy === "lookup" ? <InlineLoader label="Loading" /> : "Fetch metadata"}
          </button>
          {bundleId && <a href={getEvidenceDownloadUrl(bundleId)}>Download ZIP</a>}
        </div>
        <p>{status}</p>
      </SectionCard>
    </ESignModuleGate>
  );
};

export default ESignEvidencePage;
