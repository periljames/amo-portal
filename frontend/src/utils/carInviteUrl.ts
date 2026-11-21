export type ParsedCarInviteLocation = {
  token: string | null;
  tokens: string[];
  captureMode: boolean;
  legacyQuery: boolean;
};

const params = (value: string): URLSearchParams =>
  new URLSearchParams(value.startsWith("?") || value.startsWith("#") ? value.slice(1) : value);

export function parseCarInviteLocation(search: string, hash: string): ParsedCarInviteLocation {
  const query = params(search);
  const fragment = params(hash);
  const fragmentToken = fragment.get("token");
  const queryToken = query.get("token");
  const token = fragmentToken || queryToken;
  const captureValue = fragment.has("capture") ? fragment.get("capture") : query.get("capture");
  return {
    token,
    tokens: token ? token.split(",").map(value => value.trim()).filter(Boolean) : [],
    captureMode: captureValue === "1",
    legacyQuery: !fragmentToken && Boolean(queryToken),
  };
}

export function buildCarInviteHash(token: string, captureMode = false): string {
  const fragment = new URLSearchParams();
  fragment.set("token", token);
  if (captureMode) fragment.set("capture", "1");
  return `#${fragment.toString()}`;
}

export function buildCarInviteUrl(origin: string, token: string, captureMode = false): string {
  return `${origin.replace(/\/$/, "")}/qms/car-access${buildCarInviteHash(token, captureMode)}`;
}
