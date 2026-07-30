function normalizePathname(target: string): string | null {
  const rawPathname = target.split(/[?#]/, 1)[0] || "/";

  try {
    const pathname = decodeURIComponent(rawPathname).replace(/\\/g, "/");
    if (!pathname.startsWith("/") || pathname.startsWith("//")) return null;
    return pathname.toLowerCase();
  } catch {
    return null;
  }
}

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
 * back to themselves. Classification uses a decoded, case-normalized pathname
 * so it matches React Router's route semantics.
 */
export function resolvePostLoginReturnTarget(
  candidate: unknown,
  platformUser: boolean,
): string | null {
  if (typeof candidate !== "string") return null;

  const target = candidate.trim();
  if (!target.startsWith("/") || target.startsWith("//")) return null;

  const pathname = normalizePathname(target);
  if (!pathname) return null;
  if (isLoginRoute(pathname)) return null;
  if (isPlatformRoute(pathname) && !platformUser) return null;

  return target;
}
