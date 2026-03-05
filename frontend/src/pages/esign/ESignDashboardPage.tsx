import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import { fetchInbox, fetchInboxCount, fetchProviderReadiness, fetchTrustSummary } from "../../services/esign";
import type { InboxCount, InboxItem, ProviderReadiness, TrustSummary } from "../../types/esign";
import ESignModuleGate from "./ESignModuleGate";
import ESignNotificationBell from "../../components/esign/ESignNotificationBell";

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

const zeroCount: InboxCount = { pending_count: 0, expiring_soon_count: 0 };

const ESignDashboardPage: React.FC = () => {
  const { amoCode = "", department = "quality" } = useParams();
  const [summary, setSummary] = useState<TrustSummary>(empty);
  const [readiness, setReadiness] = useState<ProviderReadiness | null>(null);
  const [inboxCount, setInboxCount] = useState<InboxCount>(zeroCount);
  const [inboxItems, setInboxItems] = useState<InboxItem[]>([]);

  useEffect(() => {
    const qs = new URLSearchParams();
    fetchTrustSummary(qs).then(setSummary).catch(() => setSummary(empty));
    fetchProviderReadiness().then(setReadiness).catch(() => setReadiness(null));
    fetchInboxCount().then(setInboxCount).catch(() => setInboxCount(zeroCount));
    fetchInbox(new URLSearchParams({ page: "1", page_size: "5" }))
      .then((out) => setInboxItems(out.items))
      .catch(() => setInboxItems([]));
  }, []);

  return (
    <ESignModuleGate>
      <PageHeader
        title="E-Signatures"
        subtitle="Operator overview for policy, trust and verification state."
        actions={<><ESignNotificationBell /> <Link to={`/maintenance/${amoCode}/${department}/esign/requests/new`}>New Signature Request</Link></>}
      />
      <SectionCard title="Pending your signature" actions={<Link to={`/maintenance/${amoCode}/${department}/esign/inbox`}>View all</Link>}>
        <p>Action required now: {inboxCount.pending_count}</p>
        <p>Expiring soon: {inboxCount.expiring_soon_count}</p>
        <ul>
          {inboxItems.map((item) => (
            <li key={item.signer_id}>
              <strong>{item.request_title}</strong> · {item.policy_code || "Default"} ·{" "}
              {item.intent_id ? <Link to={`/maintenance/${amoCode}/${department}/esign/sign/${item.intent_id}`}>Review &amp; Sign</Link> : "No intent yet"}
            </li>
          ))}
          {!inboxItems.length && <li>No pending signature tasks.</li>}
        </ul>
      </SectionCard>
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
