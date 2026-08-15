import { useQuery } from "@tanstack/react-query";

import {
  getAdminAccountRoleCatalogue,
  type AdminAccountRoleCatalogueItem,
} from "../services/adminUsers";
import type { AccountRole } from "../services/auth";

const SAFE_LOADING_ROLE: AdminAccountRoleCatalogueItem = {
  key: "USER",
  label: "User",
  category: "GENERAL",
  description: "Standard employee self-service access.",
  aliases: [],
  regulated: false,
  workforce_role_key: null,
  can_manage_accounts: false,
  can_have_supervisor: true,
  permission_summary: ["Own roster", "Own leave", "Own attendance"],
};

export function useAdminAccountRoles(currentRole?: AccountRole | "", enabled = true) {
  const query = useQuery({
    queryKey: ["accounts", "admin", "role-catalogue"],
    queryFn: getAdminAccountRoleCatalogue,
    enabled,
    staleTime: 10 * 60_000,
  });

  const roles = query.data?.roles.length ? [...query.data.roles] : [SAFE_LOADING_ROLE];
  if (currentRole && !roles.some((role) => role.key === currentRole)) {
    roles.push({
      ...SAFE_LOADING_ROLE,
      key: currentRole,
      label: currentRole.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()),
      description: "Current account role.",
    });
  }

  const selected = currentRole ? roles.find((role) => role.key === currentRole) ?? null : null;
  return { ...query, roles, selected };
}
