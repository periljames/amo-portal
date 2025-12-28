// src/pages/DashboardPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getContext, getCachedUser } from "../services/auth";
import { decodeAmoCertFromUrl } from "../utils/amo";
import { AircraftDocument, listDocumentAlerts } from "../services/fleet";

type DepartmentId =
  | "planning"
  | "production"
  | "quality"
  | "safety"
  | "stores"
  | "engineering"
  | "workshops"
  | "admin";

const DEPT_LABEL: Record<string, string> = {
  planning: "Planning",
  production: "Production",
  quality: "Quality & Compliance",
  safety: "Safety Management",
  stores: "Procurement & Stores",
  engineering: "Engineering",
  workshops: "Workshops",
  admin: "System Admin",
};

const niceLabel = (dept: string) => DEPT_LABEL[dept] || dept;

function isAdminUser(u: any): boolean {
  if (!u) return false;
  return (
    !!u.is_superuser ||
    !!u.is_amo_admin ||
    u.role === "SUPERUSER" ||
    u.role === "AMO_ADMIN"
  );
}

function isDepartmentId(v: string): v is DepartmentId {
  return Object.prototype.hasOwnProperty.call(DEPT_LABEL, v);
}

const DashboardPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();

  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";

  const currentUser = getCachedUser();
  const isAdmin = isAdminUser(currentUser);
  const [docAlerts, setDocAlerts] = useState<AircraftDocument[] | null>(null);
  const [docAlertsError, setDocAlertsError] = useState<string | null>(null);
  const [docAlertsLoading, setDocAlertsLoading] = useState(false);

  // For normal users, this MUST be their assigned department (server-driven context).
  // We also fall back to cached user.department_id if you ever store codes there.
  const assignedDept = useMemo(() => {
    const ctxDept = (ctx.department || "").trim();
    if (ctxDept) return ctxDept;

    const userDept = (currentUser?.department_id || "").trim();
    if (userDept) return userDept;

    return null;
  }, [ctx.department, currentUser?.department_id]);

  const requestedDeptRaw = (params.department || "").trim();
  const requestedDept: string | null = requestedDeptRaw ? requestedDeptRaw : null;

  // ✅ Guard: normal users can ONLY access their assigned department.
  useEffect(() => {
    if (!currentUser) return;
    if (isAdmin) return;

    if (!assignedDept) {
      // Misconfigured account/session; bounce to AMO login
      navigate(`/maintenance/${amoSlug}/login`, { replace: true });
      return;
    }

    // Non-admins must never land in "admin"
    if (assignedDept === "admin") {
      navigate(`/maintenance/${amoSlug}/login`, { replace: true });
      return;
    }

    // If URL dept differs, hard-correct it (prevents cross-department browsing)
    if (requestedDept && requestedDept !== assignedDept) {
      navigate(`/maintenance/${amoSlug}/${assignedDept}`, { replace: true });
    }

    // If URL dept is missing, send them to assigned dept
    if (!requestedDept) {
      navigate(`/maintenance/${amoSlug}/${assignedDept}`, { replace: true });
    }
  }, [currentUser, isAdmin, assignedDept, requestedDept, amoSlug, navigate]);

  // While we are correcting routes for non-admins, render nothing to avoid flicker.
  if (
    currentUser &&
    !isAdmin &&
    assignedDept &&
    (requestedDept !== assignedDept || !requestedDept)
  ) {
    return null;
  }

  // Effective department for rendering
  const department: DepartmentId = useMemo(() => {
    if (isAdmin) {
      const d = requestedDept || ctx.department || "planning";
      return (isDepartmentId(d) ? d : "planning") as DepartmentId;
    }

    const d = assignedDept || "planning";
    return (isDepartmentId(d) ? d : "planning") as DepartmentId;
  }, [isAdmin, requestedDept, ctx.department, assignedDept]);

  const amoDisplay =
    amoSlug !== "UNKNOWN" ? decodeAmoCertFromUrl(amoSlug) : "AMO";

  const isCRSDept = department === "planning" || department === "production";
  const isSystemAdminDept = department === "admin";
  const isQualityDept = department === "quality";
  const shouldShowComplianceAlerts =
    department === "planning" ||
    department === "production" ||
    department === "quality";

  const canManageUsers =
    !!currentUser &&
    (currentUser.is_superuser ||
      currentUser.is_amo_admin ||
      currentUser.role === "SUPERUSER" ||
      currentUser.role === "AMO_ADMIN");

  const handleNewCrs = () => {
    navigate(`/maintenance/${amoSlug}/${department}/crs/new`);
  };

  const handleCreateUser = () => {
    navigate(`/maintenance/${amoSlug}/admin/users/new`);
  };

  const handleOpenQms = () => {
    navigate(`/maintenance/${amoSlug}/${department}/qms`);
  };

  useEffect(() => {
    if (!shouldShowComplianceAlerts) {
      setDocAlerts(null);
      return;
    }

    setDocAlertsLoading(true);
    setDocAlertsError(null);
    listDocumentAlerts({ due_within_days: 45 })
      .then((alerts) => setDocAlerts(alerts))
      .catch((err) => {
        setDocAlertsError(err?.message || "Could not load document alerts.");
      })
      .finally(() => setDocAlertsLoading(false));
  }, [department, shouldShowComplianceAlerts]);

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
          <h2 className="page-section__title">Certificates of Release to Service</h2>
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

      {isSystemAdminDept && (
        <section className="page-section">
          <h2 className="page-section__title">System Administration</h2>
          <p className="page-section__body">
            User account management for this AMO. Access is restricted to AMO
            Administrators and platform Superusers in line with AMO and
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

      {shouldShowComplianceAlerts && (
        <section className="page-section">
          <h2 className="page-section__title">Airworthiness document alerts</h2>
          <p className="page-section__body">
            Planning, Production, and Quality are notified when documents like C
            of A, ARC, or radio licenses are due or missing. Work on an affected
            aircraft is blocked until updated evidence is uploaded (Quality can
            override with a recorded reason).
          </p>

          {docAlertsLoading && (
            <p className="page-section__body">Loading document alerts…</p>
          )}
          {docAlertsError && (
            <p className="page-section__body error-text">{docAlertsError}</p>
          )}
          {!docAlertsLoading && !docAlertsError && (
            <>
              {(docAlerts?.length || 0) === 0 ? (
                <p className="page-section__body">
                  No document alerts found in the next 45 days.
                </p>
              ) : (
                <ul className="card-list">
                  {docAlerts?.map((alert) => (
                    <li className="card card--border" key={alert.id}>
                      <h3 className="card__title">
                        {alert.document_type.replace(/_/g, " ")} ·{" "}
                        {alert.aircraft_serial_number}
                      </h3>
                      <p className="card__subtitle">
                        Authority: {alert.authority} · Status: {alert.status}
                      </p>
                      <p className="card__body">
                        {alert.expires_on
                          ? `Expires on ${alert.expires_on}${
                              alert.days_to_expiry !== null
                                ? ` (${alert.days_to_expiry} days)`
                                : ""
                            }`
                          : "Expiry not recorded"}
                        {alert.missing_evidence && " · Evidence missing"}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>
      )}

      {isQualityDept && (
        <section className="page-section">
          <h2 className="page-section__title">Quality Management System</h2>
          <p className="page-section__body">
            Review QMS documents, audits, change requests, and distribution
            activity for {niceLabel(department)}.
          </p>
          <button
            type="button"
            className="primary-chip-btn"
            onClick={handleOpenQms}
          >
            Open QMS overview
          </button>
        </section>
      )}

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
