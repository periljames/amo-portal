// src/pages/DashboardPage.tsx
import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getContext } from "../services/auth";
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

  const handleNewCrs = () => {
    navigate(`/maintenance/${amoSlug}/${department}/crs/new`);
  };

  console.log("DashboardPage", { amoSlug, amoDisplay, department, params, ctx });

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

      {!isCRSDept && (
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
