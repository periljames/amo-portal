export type PrecacheManifestEntry = { file?: string; imports?: string[]; css?: string[]; assets?: string[] };

export function collectQmsPrecacheUrls(manifest: Record<string, PrecacheManifestEntry>): string[] {
  const visited = new Set<string>();
  const urls = new Set<string>();
  const visit = (key: string) => {
    if (visited.has(key)) return;
    visited.add(key);
    const entry = manifest[key];
    if (!entry) return;
    for (const file of [entry.file, ...(entry.css || []), ...(entry.assets || [])]) {
      if (file && (file.startsWith("assets/") || file.startsWith("pdfjs/"))) urls.add(`/${file}`);
    }
    for (const dependency of entry.imports || []) visit(dependency);
  };
  for (const key of Object.keys(manifest)) {
    if (/src\/(?:pages\/(?:qms\/|quality[^/]*\/|Quality)|features\/qms\/|components\/QMS\/)/i.test(key)) visit(key);
  }
  return [...urls].sort();
}
