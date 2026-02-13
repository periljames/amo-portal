import React from "react";
import { Navigate, useParams } from "react-router-dom";

const QualityCloseoutHubPage: React.FC = () => {
  const { amoCode, department } = useParams<{ amoCode?: string; department?: string }>();
  return <Navigate to={`/maintenance/${amoCode}/${department ?? "quality"}/qms/audits/closeout/findings`} replace />;
};

export default QualityCloseoutHubPage;
