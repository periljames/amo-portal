import { getCachedUser, getContext, type PortalUser } from "../services/auth";
import { readCachedAdminProfileState } from "../services/adminProfileMode";

export function isTenantAdmin(user: PortalUser | null | undefined): boolean {
  if (!user?.amo_id || user.is_active === false || user.is_superuser || user.role === "SUPERUSER") return false;
  if (user.is_amo_admin || user.role === "AMO_ADMIN") return true;
  if (typeof window === "undefined") return false;
  if (getCachedUser()?.id !== user.id || getCachedUser()?.amo_id !== user.amo_id) return false;
  const context = getContext();
  const aliases = user.amo_slug || user.amo_code
    ? [user.amo_slug, user.amo_code] : [context.amoSlug, context.amoCode];
  return aliases.some((code) => {
    const state = code ? readCachedAdminProfileState(code) : null;
    return Boolean(state?.eligible && state.active);
  });
}

export function userBelongsToTenant(user: PortalUser | null, amoCode: string): boolean {
  if (!user?.amo_id || user.is_active === false || user.is_superuser || user.role === "SUPERUSER") return false;
  const context = getContext();
  const aliases = [user.amo_code, user.amo_slug];
  // Compatibility for sessions issued before tenant identity was added to /auth/me.
  if (!aliases.some(Boolean)) aliases.push(context.amoCode, context.amoSlug);
  return aliases.some((alias) => alias?.toLowerCase() === amoCode.toLowerCase());
}
