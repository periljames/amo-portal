import React from "react";

import DepartmentLayoutImpl from "./DepartmentLayoutImpl";

type Props = {
  amoCode: string;
  activeDepartment: string;
  children: React.ReactNode;
  showPollingErrorBanner?: boolean;
};

const DepartmentLayout: React.FC<Props> = (props) => (
  <DepartmentLayoutImpl {...props} />
);

export default DepartmentLayout;
