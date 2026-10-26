export function isEffectivenessResponseRoute(pathname: string, search: string): boolean {
  const workspace = new URLSearchParams(search).get("workspace")?.toLowerCase();
  if (workspace === "assurance") return true;
  return /^\/maintenance\/[^/]+\/quality\/assurance(?:\/|$)/i.test(pathname);
}

