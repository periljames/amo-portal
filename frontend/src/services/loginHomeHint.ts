const HINT_PREFIX = "amodb:last-landing:";

function storageKey(loginSlug: string): string {
  return `${HINT_PREFIX}${loginSlug.trim().toLowerCase()}`;
}

function getStorage(): Storage | null {
  try {
    if (typeof globalThis === "undefined") return null;
    const storage = (globalThis as { localStorage?: Storage }).localStorage;
    return storage ?? null;
  } catch {
    return null;
  }
}

function isSafeHintPath(loginSlug: string, path: string): boolean {
  const trimmed = path.trim();
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) return false;
  if (trimmed.split(/[?#]/, 1)[0]?.split("/").some((part) => part === "." || part === "..")) return false;
  if (trimmed === "/platform/control") return true;
  const slug = encodeURIComponent(loginSlug.trim());
  const rawSlug = loginSlug.trim();
  return (
    trimmed === `/maintenance/${rawSlug}`
    || trimmed.startsWith(`/maintenance/${rawSlug}/`)
    || trimmed === `/maintenance/${slug}`
    || trimmed.startsWith(`/maintenance/${slug}/`)
  );
}

/** Remember the authenticated home route so the next password step can warm it early. */
export function rememberLoginHome(loginSlug: string, homePath: string): void {
  const storage = getStorage();
  const slug = loginSlug.trim();
  const path = homePath.trim();
  if (!storage || !slug || !path || !isSafeHintPath(slug, path)) return;
  try {
    storage.setItem(storageKey(slug), path);
  } catch {
    /* private mode / quota — skip */
  }
}

/** Public hint only: a path the user landed on before for this tenant slug. */
export function readLoginHomeHint(loginSlug: string | null | undefined): string | null {
  const storage = getStorage();
  const slug = (loginSlug || "").trim();
  if (!storage || !slug) return null;
  try {
    const value = storage.getItem(storageKey(slug));
    if (!value || !isSafeHintPath(slug, value)) return null;
    return value;
  } catch {
    return null;
  }
}
