// src/pages/DashboardPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getContext, getCachedUser } from "../services/auth";
import { getMyTrainingStatus } from "../services/training";
import type { TrainingStatusItem, TrainingStatusLabel } from "../types/training";
import { decodeAmoCertFromUrl } from "../utils/amo";

type DepartmentId =
  | "planning"
  | "production"
  | "quality"
  | "safety"
  | "stores"
  | "engineering"
  | "workshops"
  | "admin";

type SheetId =
  | "hours"
  | "airframe-typical"
  | "hard-time"
  | "engine-periodic"
  | "ops-kcaa"
  | "airframe-ads";

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
  const isEngineeringDept = department === "engineering";

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

  const handleTraining = () => {
    navigate(`/maintenance/${amoSlug}/${department}/training`);
  };

  const handleQms = () => {
    navigate(`/maintenance/${amoSlug}/${department}/qms`);
  };

  const handleAircraftImport = () => {
    navigate(`/maintenance/${amoSlug}/${department}/aircraft-import`);
  };

  const [trainingState, setTrainingState] = useState<"idle" | "loading" | "ready" | "error">(
    "idle",
  );
  const [trainingError, setTrainingError] = useState<string | null>(null);
  const [trainingItems, setTrainingItems] = useState<TrainingStatusItem[]>([]);

  useEffect(() => {
    if (!currentUser) return;
    setTrainingState("loading");
    setTrainingError(null);

    getMyTrainingStatus()
      .then((items) => {
        setTrainingItems(items);
        setTrainingState("ready");
      })
      .catch((err: any) => {
        setTrainingError(err?.message || "Unable to load training snapshot.");
        setTrainingState("error");
      });
  }, [currentUser]);

  const trainingCounts = useMemo(() => {
    const counts: Record<TrainingStatusLabel, number> = {
      OK: 0,
      DUE_SOON: 0,
      OVERDUE: 0,
      DEFERRED: 0,
      SCHEDULED_ONLY: 0,
      NOT_DONE: 0,
    };

    for (const item of trainingItems) {
      counts[item.status] += 1;
    }

    return {
      total: trainingItems.length,
      ...counts,
    };
  }, [trainingItems]);

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

      {!isSystemAdminDept && (
        <>
          <section className="page-section">
            <h2 className="page-section__title">Daily overview</h2>
            <p className="page-section__body">
              Stay on top of training compliance, ongoing work, and department priorities.
            </p>
            <div className="page-section__actions">
              <button type="button" className="primary-chip-btn" onClick={handleTraining}>
                Open My Training
              </button>
              {isCRSDept && (
                <button type="button" className="secondary-chip-btn" onClick={handleNewCrs}>
                  Create CRS
                </button>
              )}
              {isQualityDept && (
                <button type="button" className="secondary-chip-btn" onClick={handleQms}>
                  Open QMS dashboard
                </button>
              )}
              {isEngineeringDept && (
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={handleAircraftImport}
                >
                  Aircraft import
                </button>
              )}
              {canManageUsers && (
                <button type="button" className="secondary-chip-btn" onClick={handleCreateUser}>
                  Manage users
                </button>
              )}
            </div>
          </section>

          <section className="page-section">
            <div className="card">
              <div className="card-header">
                <h2>My training snapshot</h2>
                <p className="text-muted">Live status from the training service.</p>
              </div>

              {trainingState === "loading" && (
                <p className="text-muted">Loading training status…</p>
              )}
              {trainingState === "error" && (
                <div className="alert alert-error">{trainingError}</div>
              )}
              {trainingState === "ready" && (
                <>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <span className="badge badge--neutral">Total: {trainingCounts.total}</span>
                    <span className="badge badge--success">OK: {trainingCounts.OK}</span>
                    <span className="badge badge--warning">Due soon: {trainingCounts.DUE_SOON}</span>
                    <span className="badge badge--danger">Overdue: {trainingCounts.OVERDUE}</span>
                    <span className="badge badge--neutral">Deferred: {trainingCounts.DEFERRED}</span>
                  </div>

                  <div style={{ marginTop: 12 }}>
                    <button type="button" className="secondary-chip-btn" onClick={handleTraining}>
                      View full training status
                    </button>
                  </div>
                </>
              )}
            </div>
          </section>
        </>
      )}
    </DepartmentLayout>
  );
};

export default DashboardPage;
