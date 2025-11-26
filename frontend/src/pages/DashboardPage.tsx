// src/pages/DashboardPage.tsx
import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getContext, getCachedUser } from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";

const niceLabel = (dept: string) => {
  switch (dept) {
    case "planning":
      return "Planning";
    case "production":
      return "Production";
    case "quality":
      return "Quality & Compliance";
    case "safety":
      return "Safety Management";
    case "stores":
      return "Procurement & Stores";
    case "engineering":
      return "Engineering";
    case "workshops":
      return "Workshops";
    case "admin":
      return "System Admin";
    default:
      return dept;
  }
};

const DashboardPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();

  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "planning";

  const amoDisplay =
    amoSlug !== "UNKNOWN" ? decodeAmoCertFromUrl(amoSlug) : "AMO";

  const isCRSDept = department === "planning" || department === "production";
  const isSystemAdminDept = department === "admin";

  const currentUser = getCachedUser();
  const canManageUsers =
    !!currentUser &&
    (currentUser.role === "SUPERUSER" || currentUser.role === "AMO_ADMIN");

  const handleNewCrs = () => {
    navigate(`/maintenance/${amoSlug}/${department}/crs/new`);
  };

  const handleCreateUser = () => {
    navigate(`/maintenance/${amoSlug}/admin/users/new`);
  };

  console.log("DashboardPage", {
    amoSlug,
    amoDisplay,
    department,
    params,
    ctx,
    currentUser,
  });

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment={department}>
      <header className="page-header">
        <h1 className="page-header__title">
          {niceLabel(department)} · {amoDisplay}
        </h1>
        <p className="page-header__subtitle">
          Welcome to the {niceLabel(department).toLowerCase()} dashboard for AMO{" "}
          <strong>{amoDisplay}</strong>.
        </p>
      </header>

      {/* Planning / Production – CRS widget */}
      {isCRSDept && (
        <section className="page-section">
          <h2 className="page-section__title">
            Certificates of Release to Service
          </h2>
          <p className="page-section__body">
            Create, track, and download CRS forms for completed maintenance.
          </p>
          <button
            type="button"
            className="primary-chip-btn"
            onClick={handleNewCrs}
          >
            + New CRS
          </button>
        </section>
      )}

      {/* System Admin – User Management */}
      {isSystemAdminDept && (
        <section className="page-section">
          <h2 className="page-section__title">System Administration</h2>
          <p className="page-section__body">
            User account management for this AMO. Access is restricted to
            AMO Administrators and platform Superusers in line with AMO and
            regulatory requirements.
          </p>

          {canManageUsers ? (
            <div className="page-section__actions">
              <button
                type="button"
                className="primary-chip-btn"
                onClick={handleCreateUser}
              >
                + Create new user
              </button>

              {/* Placeholder for future list / search */}
              {/* <button
                type="button"
                className="secondary-chip-btn"
                onClick={() =>
                  navigate(`/maintenance/${amoSlug}/admin/users`)
                }
              >
                View all users
              </button> */}
            </div>
          ) : (
            <p className="page-section__body">
              You are signed in to the System Admin dashboard but do not have
              the required system privileges to manage user accounts. Please
              contact Quality or the AMO System Administrator.
            </p>
          )}
        </section>
      )}

      {/* Other departments – placeholder */}
      {!isCRSDept && !isSystemAdminDept && (
        <section className="page-section">
          <p className="page-section__body">
            Department widgets for {niceLabel(department)} will appear here.
          </p>
        </section>
      )}
    </DepartmentLayout>
  );
};

export default DashboardPage;
