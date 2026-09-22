/** Build a Microsoft Teams “new meeting” deep link for the selected window. */
export function teamsCreateMeetingUrl(input: {
  subject: string;
  start?: string | null;
  end?: string | null;
}): string {
  const params = new URLSearchParams();
  params.set("subject", input.subject.trim() || "Audit meeting");
  const start = toTeamsDateTime(input.start);
  const end = toTeamsDateTime(input.end);
  if (start) params.set("startTime", start);
  if (end) params.set("endTime", end);
  return `https://teams.microsoft.com/l/meeting/new?${params.toString()}`;
}

export function isTeamsMeetingUrl(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;
  try {
    const host = new URL(trimmed).hostname.toLowerCase();
    return (
      host === "teams.microsoft.com" ||
      host.endsWith(".teams.microsoft.com") ||
      host === "teams.live.com" ||
      host.endsWith(".teams.live.com")
    );
  } catch {
    return /teams\.microsoft\.com|teams\.live\.com/i.test(trimmed);
  }
}

export function auditMeetingSubject(
  type: "OPENING" | "CLOSING",
  auditTitle?: string | null,
  auditRef?: string | null,
): string {
  const label = type === "OPENING" ? "Opening meeting" : "Closing meeting";
  const title = (auditTitle || "").trim();
  const ref = (auditRef || "").trim();
  if (title && ref) return `${label} · ${ref} · ${title}`;
  if (title) return `${label} · ${title}`;
  if (ref) return `${label} · ${ref}`;
  return label;
}

function toTeamsDateTime(value?: string | null): string | null {
  const raw = (value || "").trim();
  if (!raw) return null;
  // datetime-local → ISO-like local stamp Teams accepts.
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(raw)) return `${raw}:00`;
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(raw)) return raw.slice(0, 19);
  return null;
}
