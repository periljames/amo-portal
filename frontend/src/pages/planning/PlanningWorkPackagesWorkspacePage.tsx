import React from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { PlanningForecastReadinessPage } from "./PlanningForecastReadinessPage";
import { PlanningWorkPackagesPage as PackageBuilderPage } from "./PlanningPhaseTwoPages";

export const PlanningWorkPackagesWorkspacePage: React.FC = () => {
  const { amoCode } = useParams();
  const [searchParams] = useSearchParams();

  if (searchParams.get("view") === "readiness") {
    return <PlanningForecastReadinessPage />;
  }

  return (
    <>
      <Link
        className="btn btn-secondary"
        style={{ position: "fixed", right: "1.25rem", bottom: "1.25rem", zIndex: 40 }}
        to={`/maintenance/${amoCode}/planning/work-packages?view=readiness`}
      >
        Forecast & readiness
      </Link>
      <PackageBuilderPage />
    </>
  );
};
