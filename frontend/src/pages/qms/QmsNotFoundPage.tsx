import React, { useMemo } from "react";
import { ArrowLeft, ArrowRight, SearchX } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import PageHeader from "../../components/shared/PageHeader";
import { qmsBasePath, qmsNavigationItems } from "./routes/qmsRouteRegistry";
import "../../styles/qms-overview.css";

const QmsNotFoundPage: React.FC = () => {
  const location = useLocation();
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode: string }>();
  const suggestions = useMemo(
    () => qmsNavigationItems(amoCode).filter((item) => ["command", "assurance", "control"].includes(item.section)).slice(0, 6),
    [amoCode],
  );

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <div className="qms-overview-page">
        <PageHeader
          compact
          eyebrow="Quality Management System"
          title="Quality route not found"
          subtitle="This address does not match a registered QMS workspace. It has not been redirected to the dashboard because silent fallbacks hide broken links."
          breadcrumbs={[{ label: "Quality", to: qmsBasePath(amoCode) }, { label: "Route not found" }]}
        />

        <main className="qms-not-found" role="main">
          <div className="qms-not-found__icon" aria-hidden="true"><SearchX size={26} /></div>
          <div className="qms-not-found__copy">
            <span>Requested path</span>
            <code>{location.pathname}</code>
            <h2>Use a registered Quality destination</h2>
            <p>The route may be misspelled, retired, or copied from an older QMS link. Return to the operational overview or open one of the supported workspaces below.</p>
          </div>

          <div className="qms-not-found__actions">
            <Link className="qms-overview-button qms-overview-button--primary" to={qmsBasePath(amoCode)}><ArrowLeft size={15} /> Quality overview</Link>
          </div>

          <div className="qms-not-found__suggestions" aria-label="Registered Quality destinations">
            {suggestions.map((item) => (
              <Link key={item.id} to={item.path}>
                <span>{item.navigationLabel}</span>
                <ArrowRight size={15} aria-hidden="true" />
              </Link>
            ))}
          </div>
        </main>
      </div>
    </DepartmentLayout>
  );
};

export default QmsNotFoundPage;
