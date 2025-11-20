// src/router.tsx
import React from "react";
import { Routes, Route, Navigate, useLocation, useParams } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import CRSNewPage from "./pages/CRSNewPage";
import { isAuthenticated } from "./services/auth";

// RequireAuth wrapper
const RequireAuth: React.FC<{ children: React.ReactElement }> = ({ children }) => {
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

      {/* AMO-specific login */}
      <Route path="/maintenance/:amoCode/login" element={<LoginPage />} />

      {/* Department dashboard */}
      <Route
        path="/maintenance/:amoCode/:department"
        element={
          <RequireAuth>
            <DashboardPage />
          </RequireAuth>
        }
      />

      {/* New CRS page */}
      <Route
        path="/maintenance/:amoCode/:department/crs/new"
        element={
          <RequireAuth>
            <CRSNewPage />
          </RequireAuth>
        }
      />

      {/* Default root & catch-all */}
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
};
