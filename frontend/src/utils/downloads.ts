import { handleAuthFailure } from "../services/auth";

export interface DownloadedFile {
  blob: Blob;
  filename: string;
  contentType: string | null;
}

export interface DownloadRequestOptions {
  url: string;
  method?: "GET" | "POST";
  headers?: Record<string, string>;
  body?: Document | XMLHttpRequestBodyInit | null;
  withCredentials?: boolean;
  onProgress?: (loaded: number, total?: number) => void;
  fallbackFilename?: string;
  timeoutMs?: number;
  retries?: number;
  retryDelayMs?: number;
  retryStatuses?: number[];
}

const DEFAULT_RETRY_STATUSES = [408, 409, 423, 425, 429, 500, 502, 503, 504];
const CONTENT_TYPE_EXTENSION_MAP: Record<string, string> = {
  "application/pdf": ".pdf",
  "application/zip": ".zip",
  "text/csv": ".csv",
  "application/json": ".json",
  "text/plain": ".txt",
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/webp": ".webp",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function resolveExtension(contentType: string | null): string {
  const base = (contentType || "").split(";")[0].trim().toLowerCase();
  return CONTENT_TYPE_EXTENSION_MAP[base] || "";
}

function decode5987(value: string): string {
  const normalized = value.replace(/^UTF-8''/i, "");
  try {
    return decodeURIComponent(normalized);
  } catch {
    return normalized;
  }
}

export function resolveDownloadFilename(disposition: string | null, fallback: string, contentType?: string | null): string {
  let filename = "";
  if (disposition) {
    const star = disposition.match(/filename\*=(?:UTF-8''|)([^;]+)/i);
    if (star?.[1]) {
      filename = decode5987(star[1].trim().replace(/^"|"$/g, ""));
    }
    if (!filename) {
      const plain = disposition.match(/filename=("([^"]+)"|([^;]+))/i);
      filename = (plain?.[2] || plain?.[3] || "").trim();
    }
  }
  filename = sanitizeDownloadFilename(filename || fallback || "download");
  const ext = resolveExtension(contentType || null);
  if (ext && !/\.[A-Za-z0-9]{1,8}$/.test(filename)) {
    filename += ext;
  }
  return filename;
}

export function sanitizeDownloadFilename(filename: string): string {
  const trimmed = String(filename || "download").trim().replace(/[\\/:*?"<>|]+/g, "_");
  const collapsed = trimmed.replace(/\s+/g, " ").replace(/^\.+/, "").slice(0, 180);
  return collapsed || "download";
}

export function saveDownloadedFile(file: DownloadedFile, overrideFilename?: string): void {
  const filename = sanitizeDownloadFilename(overrideFilename || file.filename || "download");
  const url = window.URL.createObjectURL(file.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => window.URL.revokeObjectURL(url), 250);
}

async function readBlobText(blob: Blob | null | undefined): Promise<string> {
  if (!blob) return "";
  try {
    return await blob.text();
  } catch {
    return "";
  }
}

export async function downloadWithXhr(options: DownloadRequestOptions): Promise<DownloadedFile> {
  const {
    url,
    method = "GET",
    headers = {},
    body = null,
    withCredentials = true,
    onProgress,
    fallbackFilename = "download",
    timeoutMs = 180_000,
    retries = 2,
    retryDelayMs = 850,
    retryStatuses = DEFAULT_RETRY_STATUSES,
  } = options;

  const attempts = Math.max(1, retries + 1);
  let lastError: Error | null = null;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await new Promise<DownloadedFile>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open(method, url);
        xhr.responseType = "blob";
        xhr.withCredentials = withCredentials;
        xhr.timeout = timeoutMs;
        Object.entries(headers).forEach(([key, value]) => xhr.setRequestHeader(key, value));

        xhr.addEventListener("progress", (event) => {
          if (!onProgress) return;
          onProgress(event.loaded, event.lengthComputable ? event.total : undefined);
        });

        xhr.addEventListener("load", async () => {
          const contentType = xhr.getResponseHeader("Content-Type") || (xhr.response as Blob | null)?.type || null;
          if (xhr.status === 401) {
            handleAuthFailure("expired");
            reject(new Error("Session expired. Please sign in again."));
            return;
          }
          if (xhr.status < 200 || xhr.status >= 300) {
            const detail = await readBlobText(xhr.response as Blob);
            const baseMessage = detail || `Download failed (${xhr.status}).`;
            const error = new Error(baseMessage);
            (error as Error & { status?: number }).status = xhr.status;
            reject(error);
            return;
          }
          resolve({
            blob: xhr.response as Blob,
            filename: resolveDownloadFilename(xhr.getResponseHeader("Content-Disposition"), fallbackFilename, contentType),
            contentType,
          });
        });

        xhr.addEventListener("error", () => reject(new Error("Network error while downloading file.")));
        xhr.addEventListener("timeout", () => reject(new Error("Download timed out. Please retry.")));
        xhr.send(body);
      });
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Download failed.");
      const status = (lastError as Error & { status?: number }).status;
      const canRetry = attempt < attempts - 1 && (!status || retryStatuses.includes(status) || /timed out|network error/i.test(lastError.message));
      if (!canRetry) break;
      await sleep(retryDelayMs * (attempt + 1));
    }
  }

  throw lastError || new Error("Download failed.");
}

export async function downloadWithFetch(
  url: string,
  init: RequestInit,
  fallbackFilename: string,
  timeoutMs = 120_000,
): Promise<DownloadedFile> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    if (response.status === 401) {
      handleAuthFailure("expired");
      throw new Error("Session expired. Please sign in again.");
    }
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(detail || `Download failed (${response.status}).`);
    }
    const contentType = response.headers.get("Content-Type") || null;
    return {
      blob: await response.blob(),
      filename: resolveDownloadFilename(response.headers.get("Content-Disposition"), fallbackFilename, contentType),
      contentType,
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Download timed out. Please retry.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}
