import { Route, Routes } from "react-router-dom";
import ManualsDashboardPage from "../../pages/manuals/ManualsDashboardPage";
import ManualOverviewPage from "../../pages/manuals/ManualOverviewPage";
import ManualReaderPage from "../../pages/manuals/ManualReaderPage";
import ManualDiffPage from "../../pages/manuals/ManualDiffPage";
import ManualWorkflowPage from "../../pages/manuals/ManualWorkflowPage";
import ManualExportsPage from "../../pages/manuals/ManualExportsPage";
import ManualMasterListPage from "../../pages/manuals/ManualMasterListPage";

export function ManualsReaderRoutes() {
  return (
    <Routes>
      <Route path="/t/:tenantSlug/manuals" element={<ManualsDashboardPage />} />
      <Route path="/t/:tenantSlug/manuals/master-list" element={<ManualMasterListPage />} />
      <Route path="/t/:tenantSlug/manuals/:manualId" element={<ManualOverviewPage />} />
      <Route path="/t/:tenantSlug/manuals/:manualId/rev/:revId/read" element={<ManualReaderPage />} />
      <Route path="/maintenance/:amoCode/:department/qms/documents/:docId/revisions/:revId/view" element={<ManualReaderPage />} />
      <Route path="/t/:tenantSlug/manuals/:manualId/rev/:revId/diff" element={<ManualDiffPage />} />
      <Route path="/t/:tenantSlug/manuals/:manualId/rev/:revId/workflow" element={<ManualWorkflowPage />} />
      <Route path="/t/:tenantSlug/manuals/:manualId/rev/:revId/exports" element={<ManualExportsPage />} />
    </Routes>
  );
}
