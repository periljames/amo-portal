import React from "react";

import AccessElevationLauncher from "../access/AccessElevationLauncher";
import AccessRealtimeBridge from "../access/AccessRealtimeBridge";
import AdminAccessRequestDock from "../access/AdminAccessRequestDock";
import DepartmentLayoutImpl from "./DepartmentLayoutImpl";

type Props = {
  amoCode: string;
  activeDepartment: string;
  children: React.ReactNode;
  showPollingErrorBanner?: boolean;
};

const DepartmentLayout: React.FC<Props> = (props) => (
  <>
    <AccessRealtimeBridge />
    <DepartmentLayoutImpl {...props} />
    <AccessElevationLauncher />
    <AdminAccessRequestDock />
  </>
);

export default DepartmentLayout;
