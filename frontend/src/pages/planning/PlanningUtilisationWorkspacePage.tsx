import React from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { PlanningUtilisationPage as PortalUtilisationControlPage } from "./PlanningUtilisationControlPage";
import { PlanningWinAirIntegrationPage } from "./PlanningWinAirIntegrationPage";
import "../../styles/winair-integration.css";

export const PlanningUtilisationWorkspacePage: React.FC = () => {
  const { amoCode } = useParams();
  const [searchParams] = useSearchParams();

  if (searchParams.get("view") === "winair") {
    return <PlanningWinAirIntegrationPage />;
  }

  return (
    <>
      <Link
        className="btn btn-secondary"
        style={{ position: "fixed", right: "1.25rem", bottom: "1.25rem", zIndex: 40 }}
        to={`/maintenance/${amoCode}/planning/utilisation-monitoring?view=winair`}
      >
        WinAir exchange
      </Link>
      <PortalUtilisationControlPage />
    </>
  );
};
