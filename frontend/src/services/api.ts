const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string;

if (!API_BASE_URL) {
  // Helpful during development
  // eslint-disable-next-line no-console
  console.warn("VITE_API_BASE_URL is not set. Check your .env.development file.");
}

export const getApiBaseUrl = () => API_BASE_URL ?? "";

export async function apiPost<T>(
  path: string,
  body: BodyInit,
  options: RequestInit = {}
): Promise<T> {
  const url = `${getApiBaseUrl()}${path}`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      ...(options.headers || {})
    },
    body,
    credentials: "include",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed with status ${res.status}`);
  }

  return (await res.json()) as T;
}
