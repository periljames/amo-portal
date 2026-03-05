import React, { useEffect, useState } from "react";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import { fetchTrustSummary } from "../../services/esign";
import type { TrustSummary } from "../../types/esign";
import ESignModuleGate from "./ESignModuleGate";

const ESignTrustSummaryPage: React.FC = () => {
  const [summary, setSummary] = useState<TrustSummary | null>(null);

  useEffect(() => {
    const query = new URLSearchParams();
    void fetchTrustSummary(query).then(setSummary).catch(() => setSummary(null));
  }, []);

  return (
    <ESignModuleGate>
      <PageHeader title="Trust Summary" subtitle="Policy, fallback, and validation aggregate reporting." />
      <SectionCard title="Aggregates">
        <pre>{JSON.stringify(summary, null, 2)}</pre>
      </SectionCard>
    </ESignModuleGate>
  );
};

export default ESignTrustSummaryPage;
