import React from "react";
import { Link, useParams } from "react-router-dom";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import ESignModuleGate from "./ESignModuleGate";

const ESignRequestsPage: React.FC = () => {
  const { amoCode = "" } = useParams();
  return (
    <ESignModuleGate>
      <PageHeader title="Signature Requests" subtitle="Backend currently exposes create/send/detail by request id." />
      <SectionCard title="Open a request">
        <p>Enter an existing request id to open details, or create a new request.</p>
        <div className="esign-actions">
          <Link to={`/maintenance/${amoCode}/quality/esign/requests/new`}>Create request</Link>
        </div>
      </SectionCard>
    </ESignModuleGate>
  );
};

export default ESignRequestsPage;
