import React from "react";

import AdminSetupCentreResendPage from "./AdminSetupCentreResendPage";
import AdminSetupWorkflowNavigator from "./adminSetup/AdminSetupWorkflowNavigator";
import "../styles/admin-setup-location.css";

const AdminSetupCentrePage: React.FC = () => (
  <>
    <AdminSetupCentreResendPage />
    <AdminSetupWorkflowNavigator />
  </>
);

export default AdminSetupCentrePage;
