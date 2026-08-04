import React from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { PlanningUtilisationPage as PortalUtilisationControlPage } from "./PlanningUtilisationControlPage";
import { PlanningWinAirIntegrationPage } from "./PlanningWinAirIntegrationPage";
import "../../styles/winair-integration.css";

export const PlanningUtilisationWorkspacePage: React.FC = () => {
  const { amoCode } = useParams();
  const [searchParams] = useSearchParams();
  const view = searchParams.get("view");

  if (view === "winair") {
    return <PlanningWinAirIntegrationPage />;
  }

  return (
    <>
      <Link
        className="winair-workspace-launch btn btn-secondary"
        to={`/maintenance/${amoCode}/planning/utilisation-monitoring?view=winair`}
      >
        WinAir exchange
      </Link>
      <PortalUtilisationControlPage />
    </>
  );
};
