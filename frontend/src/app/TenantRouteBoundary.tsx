import { getFirstAccessibleModuleRoute } from "../utils/roleAccess";
import { isTenantAdmin, userBelongsToTenant } from "../utils/tenantAccess";
import { userHasQmsRolePermission } from "./routeGuards";
import React, { useEffect, useMemo, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import {
  getCachedUser,
  getContext,
  normalizeDepartmentCode,
} from "../services/auth";
import {
  fetchAdminProfileState,
  onAdminProfileChange,
  readCachedAdminProfileState,
  type AdminProfileState,
} from "../services/adminProfileMode";
import {
  getAllowedDepartments,
  getAssignedDepartment,
  getOperationalAccessUser,
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
  "procurement",
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
  const user = getCachedUser();
  return user?.amo_slug || user?.amo_code || context.amoSlug || context.amoCode || null;
}

function isPublicTenantRoute(parts: string[]): boolean {
  return parts[2] === "login" || parts[2] === "onboarding";
}

function routeDepartment(parts: string[]): DepartmentId | null {
  const segment = normalizeDepartmentCode(parts[2] || "");
  if (segment === "ehm") return "reliability";
  if (segment && DEPARTMENT_SEGMENTS.has(segment as DepartmentId) && isDepartmentId(segment)) {
    return segment;
  }
  return null;
}

function sameTenant(left: string, right: string): boolean {
  return left.trim().toLowerCase() === right.trim().toLowerCase();
}

const TenantRouteBoundary: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const routeParts = useMemo(() => segments(location.pathname), [location.pathname]);
  const currentUser = getCachedUser();
  const isTenantRoute = routeParts[0] === "maintenance" && Boolean(routeParts[1]);
  const isPublicRoute = isTenantRoute && isPublicTenantRoute(routeParts);
  const routeTenant = isTenantRoute ? routeParts[1] : "";
  const isAdminRoute = isTenantRoute && routeParts[2] === "admin";
  const cachedAdminState = routeTenant ? readCachedAdminProfileState(routeTenant) : null;
  const [adminState, setAdminState] = useState<AdminProfileState | null>(cachedAdminState);
  const [adminStateResolved, setAdminStateResolved] = useState(Boolean(cachedAdminState));

  useEffect(() => {
    if (!isTenantRoute || isPublicRoute || !currentUser || !userBelongsToTenant(currentUser, routeTenant)) {
      setAdminState(null);
      setAdminStateResolved(true);
      return;
    }

    let active = true;
    const applyState = (state: AdminProfileState) => {
      if (!active) return;
      setAdminState(state);
      setAdminStateResolved(true);
    };

    const cached = readCachedAdminProfileState(routeTenant);
    if (cached) applyState(cached);
    else setAdminStateResolved(false);

    const unsubscribe = onAdminProfileChange(({ amoCode, userId, state }) => {
      if (userId !== currentUser.id) return;
      if (sameTenant(amoCode, routeTenant)) applyState(state);
    });

    fetchAdminProfileState(routeTenant)
      .then(applyState)
      .catch(() => applyState({ eligible: false, active: false }));

    return () => {
      active = false;
      unsubscribe();
    };
  }, [currentUser?.id, isPublicRoute, isTenantRoute, routeTenant]);

  if (!isTenantRoute || isPublicRoute || !currentUser) return <>{children}</>;

  if (currentUser.is_superuser || currentUser.role === "SUPERUSER") {
    return <Navigate to="/platform/control" replace state={{ blockedTenantPath: location.pathname }} />;
  }
  const standingAdmin = isTenantAdmin(currentUser);

  const canonicalTenant = canonicalTenantSlug();
  if (!canonicalTenant) return <Navigate to="/login" replace />;
  if (!userBelongsToTenant(currentUser, routeTenant)) {
    return <Navigate to={`/maintenance/${encodeURIComponent(canonicalTenant)}`} replace state={{ blockedTenantPath: location.pathname }} />;
  }

  const assigned = getAssignedDepartment(currentUser, getContext().department);
  const operationalUser = getOperationalAccessUser(currentUser);
  const normalAllowed = getAllowedDepartments(operationalUser, assigned).filter(
    (department): department is Exclude<DepartmentId, "admin"> => department !== "admin",
  );
  const allowed = normalAllowed;
  const home = getFirstAccessibleModuleRoute(canonicalTenant, currentUser, assigned);
  if (isAdminRoute && !standingAdmin && !adminStateResolved) {
    return (
      <div className="page-loading" role="status" aria-live="polite">
        <div className="page-loading__card">Confirming Admin profile…</div>
      </div>
    );
  }

  if (routeParts.length === 2) return <Navigate to={home} replace />;

  if (isAdminRoute) {
    if (!standingAdmin && (!adminState?.eligible || !adminState.active)) {
      return <Navigate to={home} replace state={{ blockedAdminPath: location.pathname }} />;
    }
    return <>{children}</>;
  }

  if ((routeParts[2] === "quality" || routeParts[2] === "qms") && !userHasQmsRolePermission(currentUser, "qms.dashboard.view")) {
    const fallback = `/maintenance/${encodeURIComponent(canonicalTenant)}/profile`;
    return <Navigate to={home.endsWith("/quality") ? fallback : home} replace />;
  }
  const requestedDepartment = routeDepartment(routeParts);
  if (requestedDepartment && requestedDepartment !== "admin" && !allowed.includes(requestedDepartment)) {
    return <Navigate to={home} replace state={{ blockedDepartmentPath: location.pathname }} />;
  }

  return <>{children}</>;
};

export default TenantRouteBoundary;
