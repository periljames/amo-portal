// src/router.tsx
import React from "react";
import {
  Routes,
  Route,
  Navigate,
  useLocation,
  useParams,
} from "react-router-dom";

import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import CRSNewPage from "./pages/CRSNewPage";
import AircraftImportPage from "./pages/AircraftImportPage";

import { isAuthenticated } from "./services/crs";

// Wrapper that ensures user is authenticated before showing protected pages
const RequireAuth: React.FC<{ children: React.ReactElement }> = ({
  children,
}) => {
  const location = useLocation();
  const { amoCode } = useParams<{ amoCode?: string }>();

  if (!isAuthenticated()) {
    const target = amoCode ? `/maintenance/${amoCode}/login` : "/login";

    return (
      <Navigate
        to={target}
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }

  return children;
};

export const AppRouter: React.FC = () => {
  return (
    <Routes>
      {/* Global login */}
      <Route path="/login" element={<LoginPage />} />

      {/* AMO-specific login, e.g. /maintenance/XLK/login */}
      <Route path="/maintenance/:amoCode/login" element={<LoginPage />} />

      {/* Department dashboard, e.g. /maintenance/XLK/engineering */}
      <Route
        path="/maintenance/:amoCode/:department"
        element={
          <RequireAuth>
            <DashboardPage />
          </RequireAuth>
        }
      />

      {/* New CRS: /maintenance/XLK/engineering/crs/new */}
      <Route
        path="/maintenance/:amoCode/:department/crs/new"
        element={
          <RequireAuth>
            <CRSNewPage />
          </RequireAuth>
        }
      />

      {/* Aircraft import: /maintenance/XLK/engineering/aircraft-import */}
      <Route
        path="/maintenance/:amoCode/:department/aircraft-import"
        element={
          <RequireAuth>
            <AircraftImportPage />
          </RequireAuth>
        }
      />

      {/* Default root & catch-all -> login */}
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
};
