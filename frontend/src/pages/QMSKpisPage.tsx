import React from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import QMSLayout from "../components/QMS/QMSLayout";
import { getContext } from "../services/auth";
import { qmsGetCockpitSnapshot } from "../services/qms";

const QMSKpisPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["qms-cockpit-snapshot", amoCode, department],
    queryFn: () => qmsGetCockpitSnapshot({ domain: "AMO" }),
  });

  return (
    <QMSLayout amoCode={amoCode} department={department} title="QMS KPIs" subtitle="Snapshot metrics from backend cockpit data.">
      <div className="qms-header__actions"><button type="button" className="secondary-chip-btn" onClick={() => refetch()}>Refresh</button></div>
      {isLoading ? <div className="qms-card">Loading snapshot…</div> : null}
      {error ? <div className="qms-card">Unable to load snapshot.</div> : null}
      {data ? (
        <div className="qms-grid" style={{ gridTemplateColumns: "repeat(3, minmax(0,1fr))" }}>
          <div className="qms-card"><h4>Audits open</h4><div>{data.audits_open}</div></div>
          <div className="qms-card"><h4>Findings overdue</h4><div>{data.findings_overdue}</div></div>
          <div className="qms-card"><h4>CARs overdue</h4><div>{data.cars_overdue}</div></div>
          <div className="qms-card"><h4>Change requests open</h4><div>{data.change_requests_open}</div></div>
          <div className="qms-card"><h4>Pending acknowledgements</h4><div>{data.pending_acknowledgements}</div></div>
          <div className="qms-card"><h4>Generated</h4><div>{new Date(data.generated_at).toLocaleString()}</div></div>
        </div>
      ) : null}
    </QMSLayout>
  );
};

export default QMSKpisPage;
