/** Internal keys belong in requests, never in a person's visible label. */
export function personDisplay(value?: string | null, fallback = "Person unavailable"): string {
  const name = value?.trim();
  if (!name || /\bID[-_][A-Z0-9_-]+\b/i.test(name) || /^[a-f0-9]{24,64}$/i.test(name)
    || /[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}/i.test(name)) return fallback;
  return name;
}
