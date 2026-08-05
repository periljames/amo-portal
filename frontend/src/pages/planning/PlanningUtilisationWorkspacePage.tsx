import React from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import AircraftImportPage from "../AircraftImportPage";
import { PlanningUtilisationPage as PortalUtilisationControlPage } from "./PlanningUtilisationControlPage";
import { PlanningWinAirIntegrationPage } from "./PlanningWinAirIntegrationPage";
import "../../styles/winair-integration.css";

export const PlanningUtilisationWorkspacePage: React.FC = () => {
  const { amoCode } = useParams();
  const [searchParams] = useSearchParams();
  const view = searchParams.get("view");

  if (view === "winair") return <PlanningWinAirIntegrationPage />;
  if (view === "induction") return <AircraftImportPage />;

  return (
    <>
      <div style={{ position: "fixed", right: "1.25rem", bottom: "1.25rem", zIndex: 40, display: "flex", gap: "0.5rem" }}>
        <Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/utilisation-monitoring?view=induction`}>Aircraft induction</Link>
        <Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/utilisation-monitoring?view=winair`}>WinAir exchange</Link>
      </div>
      <PortalUtilisationControlPage />
    </>
  );
};