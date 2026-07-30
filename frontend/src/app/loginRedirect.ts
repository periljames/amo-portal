function isLoginRoute(pathname: string): boolean {
  return pathname === "/login" || /^\/maintenance\/[^/]+\/login\/?$/.test(pathname);
}

function isPlatformRoute(pathname: string): boolean {
  return pathname === "/platform" || pathname.startsWith("/platform/");
}

/**
 * Resolve a same-origin post-login return target for the authenticated account.
 *
 * Route state is untrusted input. In particular, tenant users must never be
 * returned to the global platform console, and login routes must not redirect
 * back to themselves.
 */
export function resolvePostLoginReturnTarget(
  candidate: unknown,
  platformUser: boolean,
): string | null {
  if (typeof candidate !== "string") return null;

  const target = candidate.trim();
  if (!target.startsWith("/") || target.startsWith("//")) return null;

  const pathname = target.split(/[?#]/, 1)[0] || "/";
  if (isLoginRoute(pathname)) return null;
  if (isPlatformRoute(pathname) && !platformUser) return null;

  return target;
}
