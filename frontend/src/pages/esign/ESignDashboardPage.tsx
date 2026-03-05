import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import { fetchProviderReadiness, fetchTrustSummary } from "../../services/esign";
import type { ProviderReadiness, TrustSummary } from "../../types/esign";
import ESignModuleGate from "./ESignModuleGate";

const empty: TrustSummary = {
  total_requests: 0,
  completed_requests: 0,
  appearance_only_completions: 0,
  crypto_signed_completions: 0,
  timestamped_completions: 0,
  fallback_count: 0,
  policy_violation_count: 0,
  validation_failure_count: 0,
};

const ESignDashboardPage: React.FC = () => {
  const { amoCode = "" } = useParams();
  const [summary, setSummary] = useState<TrustSummary>(empty);
  const [readiness, setReadiness] = useState<ProviderReadiness | null>(null);

  useEffect(() => {
    const qs = new URLSearchParams();
    fetchTrustSummary(qs).then(setSummary).catch(() => setSummary(empty));
    fetchProviderReadiness().then(setReadiness).catch(() => setReadiness(null));
  }, []);

  return (
    <ESignModuleGate>
      <PageHeader
        title="E-Signatures"
        subtitle="Operator overview for policy, trust and verification state."
        actions={<Link to={`/maintenance/${amoCode}/quality/esign/requests/new`}>New Signature Request</Link>}
      />
      <SectionCard title="Trust snapshot">
        <div className="esign-grid">
          <div>Total requests: {summary.total_requests}</div>
          <div>Completed: {summary.completed_requests}</div>
          <div>Appearance-only: {summary.appearance_only_completions}</div>
          <div>Crypto-signed: {summary.crypto_signed_completions}</div>
          <div>Fallback count: {summary.fallback_count}</div>
          <div>Policy violations: {summary.policy_violation_count}</div>
          <div>Validation failures: {summary.validation_failure_count}</div>
          <div>Provider readiness: {readiness?.health_ok ? "Healthy" : "Needs attention"}</div>
        </div>
      </SectionCard>
    </ESignModuleGate>
  );
};

export default ESignDashboardPage;
