import React from "react";

import AccessElevationLauncher from "../access/AccessElevationLauncher";
import AccessRealtimeBridge from "../access/AccessRealtimeBridge";
import AdminAccessRequestDock from "../access/AdminAccessRequestDock";
import { useAccessRevision } from "../../hooks/useAccessRevision";
import DepartmentLayoutImpl from "./DepartmentLayoutImpl";

type Props = {
  amoCode: string;
  activeDepartment: string;
  children: React.ReactNode;
  showPollingErrorBanner?: boolean;
};

const DepartmentLayout: React.FC<Props> = (props) => {
  // Reading the revision is intentional: it re-renders the shell after the
  // realtime bridge refreshes the cached user, so navigation/module visibility
  // changes without a page reload or a new login.
  useAccessRevision();

  return (
    <>
      <AccessRealtimeBridge />
      <DepartmentLayoutImpl {...props} />
      <AccessElevationLauncher />
      <AdminAccessRequestDock />
    </>
  );
};

export default DepartmentLayout;
