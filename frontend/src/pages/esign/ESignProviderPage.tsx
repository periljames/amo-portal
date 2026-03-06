import React, { useEffect, useState } from "react";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import { fetchProviderReadiness } from "../../services/esign";
import type { ProviderReadiness } from "../../types/esign";
import ESignModuleGate from "./ESignModuleGate";

const ESignProviderPage: React.FC = () => {
  const [data, setData] = useState<ProviderReadiness | null>(null);

  const refresh = async () => {
    setData(await fetchProviderReadiness());
  };

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <ESignModuleGate>
      <PageHeader title="Provider Readiness" subtitle="Operational readiness for appearance, crypto, and timestamp policies." />
      <SectionCard title="Status" actions={<button type="button" onClick={() => void refresh()}>Refresh</button>}>
        <pre>{JSON.stringify(data, null, 2)}</pre>
      </SectionCard>
    </ESignModuleGate>
  );
};

export default ESignProviderPage;
