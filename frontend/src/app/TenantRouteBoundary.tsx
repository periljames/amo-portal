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

function routeDepartment(parts: string[]): DepartmentId | null {
  const segment = normalizeDepartmentCode(parts[2] || "");
  if (segment === "ehm") return "reliability";
  if (segment && DEPARTMENT_SEGMENTS.has(segment as DepartmentId) && isDepartmentId(segment)) return segment;
  return null;
}

const TenantRouteBoundary: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const routeParts = useMemo(() => segments(location.pathname), [location.pathname]);
  const currentUser = getCachedUser();
  const isTenantRoute = routeParts[0] === "maintenance" && Boolean(routeParts[1]);
  const routeTenant = isTenantRoute ? routeParts[1] : "";
  const isAdminRoute = isTenantRoute && routeParts[2] === "admin";
  const isEligibleAdmin = Boolean(currentUser && isAdminUser(currentUser));
  const cachedAdminState = routeTenant ? readCachedAdminProfileState(routeTenant) : null;
  const [adminState, setAdminState] = useState<AdminProfileState | null>(cachedAdminState);
  const [adminStateResolved, setAdminStateResolved] = useState(!isEligibleAdmin || Boolean(cachedAdminState));

  useEffect(() => {
    if (!isTenantRoute || !currentUser || !isAdminUser(currentUser)) {
      setAdminState(null);
      setAdminStateResolved(true);
      return;
    }
    const cached = readCachedAdminProfileState(routeTenant);
    if (cached) {
      setAdminState(cached);
      setAdminStateResolved(true);
    } else {
      setAdminStateResolved(false);
    }
    let active = true;
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
  }, [currentUser?.id, isTenantRoute, routeTenant]);

  if (!isTenantRoute || isPublicTenantRoute(routeParts) || !currentUser) return <>{children}</>;

  if (currentUser.is_superuser || currentUser.role === "SUPERUSER") {
    return <Navigate to="/platform/control" replace state={{ blockedTenantPath: location.pathname }} />;
  }

  const canonicalTenant = canonicalTenantSlug();
  if (!canonicalTenant) return <Navigate to="/login" replace />;
  if (!tenantMatches(routeTenant)) {
    return <Navigate to={`/maintenance/${encodeURIComponent(canonicalTenant)}`} replace state={{ blockedTenantPath: location.pathname }} />;
  }

  if (isEligibleAdmin && !adminStateResolved) {
    return <div className="page-loading" role="status" aria-live="polite"><div className="page-loading__card">Confirming access profile…</div></div>;
  }

  const assigned = getAssignedDepartment(currentUser, getContext().department);
  const allAllowed = getAllowedDepartments(currentUser, assigned).filter(
    (department): department is Exclude<DepartmentId, "admin"> => department !== "admin",
  );
  const normalAllowed: Array<Exclude<DepartmentId, "admin">> =
    assigned && assigned !== "admin" ? [assigned] : [];
  const allowed = isEligibleAdmin && adminState?.active
    ? allAllowed
    : normalAllowed;
  const homeDepartment = allowed[0];

  if (!homeDepartment) {
    return <Navigate to={`/maintenance/${encodeURIComponent(canonicalTenant)}/login`} replace state={{ accessConfigurationError: true }} />;
  }
  const home = departmentHome(canonicalTenant, homeDepartment);

  if (routeParts.length === 2) return <Navigate to={home} replace />;

  if (isAdminRoute) {
    if (!isEligibleAdmin || !adminState?.active) {
      return <Navigate to={home} replace state={{ blockedAdminPath: location.pathname }} />;
    }
    return <>{children}</>;
  }

  const requestedDepartment = routeDepartment(routeParts);
  if (requestedDepartment && requestedDepartment !== "admin" && !allowed.includes(requestedDepartment)) {
    return <Navigate to={home} replace state={{ blockedDepartmentPath: location.pathname }} />;
  }

  return <>{children}</>;
};

export default TenantRouteBoundary;
