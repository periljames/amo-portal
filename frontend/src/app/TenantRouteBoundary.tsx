import React, { useEffect, useMemo, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import {
  getCachedUser,
  getContext,
  normalizeDepartmentCode,
} from "../services/auth";
import {
  fetchAdminProfileState,
  readCachedAdminProfileState,
  type AdminProfileState,
} from "../services/adminProfileMode";
import {
  getAllowedDepartments,
  getAssignedDepartment,
  isAdminUser,
  isDepartmentId,
  type DepartmentId,
} from "../utils/departmentAccess";

const DEPARTMENT_SEGMENTS = new Set<DepartmentId>([
  "planning",
  "production",
  "maintenance",
  "document-control",
  "quality",
  "reliability",
  "safety",
  "stores",
  "workshops",
  "admin",
]);

function segments(pathname: string): string[] {
  return pathname.split("/").filter(Boolean).map((value) => {
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  });
}

function canonicalTenantSlug(): string | null {
  const context = getContext();
  return context.amoSlug || context.amoCode || null;
}

function tenantMatches(routeTenant: string): boolean {
  const context = getContext();
  const candidates = [context.amoSlug, context.amoCode]
    .filter((value): value is string => Boolean(value))
    .map((value) => value.trim().toLowerCase());
  return candidates.includes(routeTenant.trim().toLowerCase());
}

function departmentHome(tenant: string, department: Exclude<DepartmentId, "admin">): string {
  return `/maintenance/${encodeURIComponent(tenant)}/${department}`;
}

function isPublicTenantRoute(parts: string[]): boolean {
  return parts[2] === "login" || parts[2] === "onboarding";
}

const TenantRouteBoundary: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const routeParts = useMemo(() => segments(location.pathname), [location.pathname]);
  const currentUser = getCachedUser();
  const isTenantRoute = routeParts[0] === "maintenance" && Boolean(routeParts[1]);
  const routeTenant = isTenantRoute ? routeParts[1] : "";
  const isAdminRoute = isTenantRoute && routeParts[2] === "admin";
  const [adminState, setAdminState] = useState<AdminProfileState | null>(() => (
    routeTenant ? readCachedAdminProfileState(routeTenant) : null
  ));
  const [adminStateResolved, setAdminStateResolved] = useState(!isAdminRoute);

  useEffect(() => {
    if (!isAdminRoute || !currentUser || !isAdminUser(currentUser)) {
      setAdminStateResolved(true);
      return;
    }
    const cached = readCachedAdminProfileState(routeTenant);
    if (cached) {
      setAdminState(cached);
      setAdminStateResolved(true);
      return;
    }
    let active = true;
    setAdminStateResolved(false);
    fetchAdminProfileState(routeTenant)
      .then((state) => {
        if (!active) return;
        setAdminState(state);
        setAdminStateResolved(true);
      })
      .catch(() => {
        if (!active) return;
        setAdminState({ eligible: false, active: false });
        setAdminStateResolved(true);
      });
    return () => { active = false; };
  }, [currentUser?.id, isAdminRoute, routeTenant]);

  if (!isTenantRoute || isPublicTenantRoute(routeParts) || !currentUser) return <>{children}</>;

  if (currentUser.is_superuser || currentUser.role === "SUPERUSER") {
    return <Navigate to="/platform/control" replace state={{ blockedTenantPath: location.pathname }} />;
  }

  const canonicalTenant = canonicalTenantSlug();
  if (!canonicalTenant) return <Navigate to="/login" replace />;
  if (!tenantMatches(routeTenant)) {
    return <Navigate to={`/maintenance/${encodeURIComponent(canonicalTenant)}`} replace state={{ blockedTenantPath: location.pathname }} />;
  }

  const assigned = getAssignedDepartment(currentUser, getContext().department);
  const allowed = getAllowedDepartments(currentUser, assigned).filter(
    (department): department is Exclude<DepartmentId, "admin"> => department !== "admin",
  );
  const homeDepartment: Exclude<DepartmentId, "admin"> =
    assigned && assigned !== "admin" && allowed.includes(assigned)
      ? assigned
      : allowed[0] || "planning";
  const home = departmentHome(canonicalTenant, homeDepartment);

  // Resolve the tenant root before the old route-level default resolver can send
  // an administrator back into /admin and create an inactive-profile loop.
  if (routeParts.length === 2) return <Navigate to={home} replace />;

  if (isAdminRoute) {
    if (!isAdminUser(currentUser)) return <Navigate to={home} replace state={{ blockedAdminPath: location.pathname }} />;
    if (!adminStateResolved) {
      return <div className="page-loading" role="status" aria-live="polite"><div className="page-loading__card">Confirming Admin profile…</div></div>;
    }
    if (!adminState?.active) return <Navigate to={home} replace state={{ blockedAdminPath: location.pathname }} />;
    return <>{children}</>;
  }

  const requested = normalizeDepartmentCode(routeParts[2] || "");
  if (requested && DEPARTMENT_SEGMENTS.has(requested as DepartmentId) && isDepartmentId(requested)) {
    if (!allowed.includes(requested as Exclude<DepartmentId, "admin">)) {
      return <Navigate to={home} replace state={{ blockedDepartmentPath: location.pathname }} />;
    }
  }

  return <>{children}</>;
};

export default TenantRouteBoundary;
