import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import SectionLoader from "../../components/loading/SectionLoader";
import { fetchInbox } from "../../services/esign";
import type { InboxItem } from "../../types/esign";
import ESignModuleGate from "./ESignModuleGate";
import ESignNotificationBell from "../../components/esign/ESignNotificationBell";
import { buildInboxQuery, isInboxEmpty } from "./inboxState";

const ESignInboxPage: React.FC = () => {
  const { amoCode = "", department = "quality" } = useParams();
  const [statusFilter, setStatusFilter] = useState("PENDING");
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<InboxItem[]>([]);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const out = await fetchInbox(buildInboxQuery({ status: statusFilter, page: 1, pageSize: 25 }));
      setItems(out.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load signing inbox");
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [statusFilter]);

  return (
    <ESignModuleGate>
      <PageHeader title="Action required" subtitle="Internal signature requests that require your approval." actions={<ESignNotificationBell />} />
      <SectionCard title="Filters">
        <label htmlFor="esign-inbox-status">Status</label>{" "}
        <select id="esign-inbox-status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="PENDING">Pending</option>
          <option value="VIEWED">Viewed</option>
          <option value="APPROVED">Approved</option>
          <option value="DECLINED">Declined</option>
        </select>
      </SectionCard>
      <SectionCard title="Pending your signature">
        {loading ? <SectionLoader title="Loading signing inbox" message="Checking requests awaiting your approval" phase="loading" /> : null}
        {error ? <p>{error}</p> : null}
        {!loading && !error && isInboxEmpty(items) ? <p>No signature actions required for this filter.</p> : null}
        {!loading && !error && !isInboxEmpty(items) ? (
          <table className="esign-inbox-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Policy required</th>
                <th>Expires</th>
                <th>Requested by</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.signer_id}>
                  <td>{item.request_title}</td>
                  <td>{item.policy_code || "Default"}</td>
                  <td>{item.expires_at ? new Date(item.expires_at).toLocaleString() : "No expiry"}</td>
                  <td>{item.requested_by || "Unknown"}</td>
                  <td>{item.signer_status}</td>
                  <td>
                    {item.intent_id ? (
                      <Link to={`/maintenance/${amoCode}/${department}/esign/sign/${item.intent_id}`}>Review &amp; Sign</Link>
                    ) : (
                      <Link to={`/maintenance/${amoCode}/${department}/esign/requests/${item.signature_request_id}`}>Open request</Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </SectionCard>
    </ESignModuleGate>
  );
};

export default ESignInboxPage;
