// src/services/training.ts
// - Training service for AMO Portal.
// - Uses generic HTTP helpers from src/services/crs.ts (apiGet/apiPost).
// - All calls are AMO-scoped via backend (amo_id derived from JWT).
//
// Backend endpoints (router: backend/amodb/apps/training/router.py):
//   * GET  /training/courses
//   * GET  /training/courses/:course_pk
//   * POST /training/courses
//   * PUT  /training/courses/:course_pk
//
//   * GET  /training/events
//   * POST /training/events
//   * PUT  /training/events/:event_id
//
//   * POST /training/event-participants
//   * PUT  /training/event-participants/:participant_id
//
//   * GET  /training/records
//   * POST /training/records
//
//   * POST /training/deferrals
//   * PUT  /training/deferrals/:deferral_id
//
//   * GET  /training/status/me
//   * GET  /training/status/users/:user_id
//
// Permissions:
//   - Read endpoints use authHeaders() (any logged-in user in same AMO).
//   - Mutating endpoints require Quality / AMO Admin / Superuser etc.
//     Enforcement lives in backend _require_training_editor.

import { apiDelete, apiGet, apiPost, apiPut } from "./crs";
import { authHeaders, handleAuthFailure } from "./auth";
import { downloadWithXhr, downloadWithFetch, type DownloadedFile, saveDownloadedFile } from "../utils/downloads";
import { getApiBaseUrl } from "./config";

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

import type {
  TrainingCourseRead,
  TrainingCourseCreate,
  TrainingCourseUpdate,
  TrainingEventRead,
  TrainingEventCreate,
  TrainingEventUpdate,
  TrainingEventBatchScheduleCreate,
  TrainingEventBatchScheduleRead,
  TrainingAutoGroupScheduleCreate,
  TrainingAutoGroupScheduleRead,
  TrainingEventParticipantRead,
  TrainingEventParticipantCreate,
  TrainingEventParticipantUpdate,
  TrainingRecordRead,
  TrainingRecordUpdate,
  TrainingRecordCreate,
  TrainingDeferralRequestRead,
  TrainingDeferralRequestCreate,
  TrainingDeferralRequestUpdate,
  TrainingStatusItem,
  TrainingNotificationRead,
  TrainingNotificationMarkRead,
  CourseImportSummary,
  TrainingAccessState,
  TrainingRequirementCreate,
  TrainingRequirementRead,
  TrainingRequirementUpdate,
  TrainingRecordImportSummary,
  TrainingCertificateArtifactOptions,
} from "../types/training";

export interface TrainingUserDetailBundle {
  user: import("./adminUsers").AdminUserRead;
  hire_date: string | null;
  status_items: TrainingStatusItem[];
  records: TrainingRecordRead[];
  records_total: number;
  deferrals: TrainingDeferralRequestRead[];
  deferrals_total: number;
  files: TrainingFileRead[];
  files_total: number;
  upcoming_events: TrainingEventRead[];
  upcoming_events_total: number;
}


export type TrainingFileReviewStatus = "PENDING" | "APPROVED" | "REJECTED";

export type TrainingFileRead = {
  id: string;
  amo_id: string;
  owner_user_id: string;
  kind: string;
  course_id?: string | null;
  event_id?: string | null;
  record_id?: string | null;
  deferral_request_id?: string | null;
  original_filename: string;
  content_type?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
  storage_path: string;
  review_status: TrainingFileReviewStatus;
  reviewed_at?: string | null;
  reviewed_by_user_id?: string | null;
  review_comment?: string | null;
  uploaded_by_user_id?: string | null;
  uploaded_at: string;
};

export type TransferProgress = {
  loadedBytes: number;
  totalBytes?: number;
  percent?: number;
  megaBytesPerSecond: number;
  megaBitsPerSecond: number;
};

function applyXhrHeaders(xhr: XMLHttpRequest, headersInit?: HeadersInit): void {
  const headers = new Headers(headersInit);
  headers.forEach((value, key) => {
    xhr.setRequestHeader(key, value);
  });
}

const TRAINING_SERVICE_CACHE_PREFIX = "amoportal:training-service-cache:";
const trainingMemoryCache = new Map<string, { expiresAt: number; value: unknown }>();
const trainingInFlight = new Map<string, Promise<unknown>>();

function cloneCachedValue<T>(value: T): T {
  try {
    return typeof structuredClone === "function" ? structuredClone(value) : JSON.parse(JSON.stringify(value));
  } catch {
    return value;
  }
}

function readTrainingCache<T>(key: string): T | null {
  const now = Date.now();
  const memory = trainingMemoryCache.get(key);
  if (memory && memory.expiresAt > now) return cloneCachedValue(memory.value as T);
  if (memory) trainingMemoryCache.delete(key);
  try {
    const raw = window.sessionStorage.getItem(`${TRAINING_SERVICE_CACHE_PREFIX}${key}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { expiresAt?: number; value?: T };
    if (!parsed || typeof parsed.expiresAt !== "number" || parsed.expiresAt <= now) {
      window.sessionStorage.removeItem(`${TRAINING_SERVICE_CACHE_PREFIX}${key}`);
      return null;
    }
    trainingMemoryCache.set(key, { expiresAt: parsed.expiresAt, value: parsed.value });
    return cloneCachedValue(parsed.value as T);
  } catch {
    return null;
  }
}

function writeTrainingCache<T>(key: string, ttlMs: number, value: T): T {
  const expiresAt = Date.now() + ttlMs;
  trainingMemoryCache.set(key, { expiresAt, value: cloneCachedValue(value) });
  try {
    window.sessionStorage.setItem(`${TRAINING_SERVICE_CACHE_PREFIX}${key}`, JSON.stringify({ expiresAt, value }));
  } catch {
    // ignore storage failures
  }
  return cloneCachedValue(value);
}

export function invalidateTrainingServiceCache(match?: string): void {
  const matcher = match ? `${TRAINING_SERVICE_CACHE_PREFIX}${match}` : null;
  for (const key of [...trainingMemoryCache.keys()]) {
    if (!match || key.includes(match)) trainingMemoryCache.delete(key);
  }
  try {
    for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
      const storageKey = window.sessionStorage.key(index);
      if (!storageKey) continue;
      if (!storageKey.startsWith(TRAINING_SERVICE_CACHE_PREFIX)) continue;
      if (!matcher || storageKey.includes(matcher)) window.sessionStorage.removeItem(storageKey);
    }
  } catch {
    // ignore storage failures
  }
}

async function cachedTrainingGet<T>(key: string, ttlMs: number, fetcher: () => Promise<T>, force = false): Promise<T> {
  if (!force) {
    const cached = readTrainingCache<T>(key);
    if (cached != null) return cached;
  }
  const inFlight = trainingInFlight.get(key) as Promise<T> | undefined;
  if (inFlight) return inFlight.then((value) => cloneCachedValue(value));
  const promise = fetcher()
    .then((value) => writeTrainingCache(key, ttlMs, value))
    .finally(() => {
      trainingInFlight.delete(key);
    });
  trainingInFlight.set(key, promise as Promise<unknown>);
  return promise.then((value) => cloneCachedValue(value));
}


// ---------------------------------------------------------------------------
// COURSES
// ---------------------------------------------------------------------------

export interface ListCoursesParams {
  include_inactive?: boolean;
  limit?: number;
  offset?: number;
}

/**
 * List training courses for the current AMO.
 */
export async function listTrainingCourses(
  params: ListCoursesParams = {},
): Promise<TrainingCourseRead[]> {
  const sp = new URLSearchParams();
  if (params.include_inactive) {
    sp.set("include_inactive", "true");
  }
  if (typeof params.limit === "number" && Number.isFinite(params.limit)) {
    sp.set("limit", String(Math.max(1, Math.trunc(params.limit))));
  }
  if (typeof params.offset === "number" && Number.isFinite(params.offset) && params.offset > 0) {
    sp.set("offset", String(Math.trunc(params.offset)));
  }

  const qs = sp.toString();
  const path = qs ? `/training/courses?${qs}` : "/training/courses";

  return cachedTrainingGet(`courses:${qs || "all"}`, 5 * 60_000, () =>
    apiGet<TrainingCourseRead[]>(path, {
      headers: authHeaders(),
    }),
  );
}

/**
 * Get a single training course by backend PK.
 */
export async function getTrainingCourse(
  coursePk: string,
): Promise<TrainingCourseRead> {
  return apiGet<TrainingCourseRead>(`/training/courses/${encodeURIComponent(coursePk)}`, {
    headers: authHeaders(),
  });
}

/**
 * Create a new training course (Quality / AMO admin only).
 */
export async function createTrainingCourse(
  payload: TrainingCourseCreate,
): Promise<TrainingCourseRead> {
  const created = await apiPost<TrainingCourseRead>("/training/courses", payload, {
    headers: authHeaders(),
  });
  invalidateTrainingServiceCache();
  return created;
}

/**
 * Update an existing training course (Quality / AMO admin only).
 */
export async function updateTrainingCourse(
  coursePk: string,
  payload: TrainingCourseUpdate,
): Promise<TrainingCourseRead> {
  // There is no dedicated apiPut helper exported, so we reuse apiPost
  // with the conventional REST pattern of using PUT at the fetch layer
  // (see implementation of request<T> in crs.ts).
  const updated = await apiPost<TrainingCourseRead>(
    `/training/courses/${encodeURIComponent(coursePk)}`,
    payload,
    {
      method: "PUT",
      headers: authHeaders(),
    } as RequestInit,
  );
  invalidateTrainingServiceCache();
  return updated;
}

export async function importTrainingCoursesWorkbook(
  file: File,
  opts?: { dryRun?: boolean; sheetName?: string; onProgress?: (progress: TransferProgress) => void }
): Promise<CourseImportSummary> {
  const dryRun = opts?.dryRun ?? true;
  const sheetName = opts?.sheetName ?? "Courses";
  const onProgress = opts?.onProgress;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const startedAt = performance.now();
    const apiBaseUrl = getApiBaseUrl();
    const qs = new URLSearchParams({
      dry_run: String(dryRun),
      sheet_name: sheetName,
    });
    xhr.open("POST", `${apiBaseUrl}/training/courses/import?${qs.toString()}`);
    applyXhrHeaders(xhr, authHeaders());

    xhr.upload.addEventListener("progress", (event) => {
      if (!onProgress) return;
      const total = event.lengthComputable ? event.total : undefined;
      onProgress(buildSpeed(event.loaded, total, startedAt));
    });

    xhr.addEventListener("load", () => {
      if (xhr.status === 401) {
        handleAuthFailure("expired");
        reject(new Error("Session expired. Please sign in again."));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(xhr.responseText || `Request failed (${xhr.status})`));
        return;
      }
      try {
        resolve(JSON.parse(xhr.responseText) as CourseImportSummary);
      } catch {
        reject(new Error("Invalid courses import response."));
      }
    });
    xhr.addEventListener("error", () => reject(new Error("Network error while importing courses workbook.")));

    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}



export async function importTrainingRecordsWorkbook(
  file: File,
  opts?: { dryRun?: boolean; sheetName?: string; onProgress?: (progress: TransferProgress) => void }
): Promise<TrainingRecordImportSummary> {
  const dryRun = opts?.dryRun ?? true;
  const sheetName = opts?.sheetName ?? "Training";
  const onProgress = opts?.onProgress;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const startedAt = performance.now();
    const apiBaseUrl = getApiBaseUrl();
    const qs = new URLSearchParams({
      dry_run: String(dryRun),
      sheet_name: sheetName,
    });
    xhr.open("POST", `${apiBaseUrl}/training/records/import?${qs.toString()}`);
    applyXhrHeaders(xhr, authHeaders());

    xhr.upload.addEventListener("progress", (event) => {
      if (!onProgress) return;
      const total = event.lengthComputable ? event.total : undefined;
      onProgress(buildSpeed(event.loaded, total, startedAt));
    });

    xhr.addEventListener("load", () => {
      if (xhr.status === 401) {
        handleAuthFailure("expired");
        reject(new Error("Session expired. Please sign in again."));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(xhr.responseText || `Request failed (${xhr.status})`));
        return;
      }
      try {
        resolve(JSON.parse(xhr.responseText) as TrainingRecordImportSummary);
      } catch {
        reject(new Error("Invalid training records import response."));
      }
    });
    xhr.addEventListener("error", () => reject(new Error("Network error while importing training records workbook.")));

    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}

// ---------------------------------------------------------------------------
// REQUIREMENTS
// ---------------------------------------------------------------------------


export interface ListTrainingRequirementsParams {
  include_inactive?: boolean;
  limit?: number;
  offset?: number;
}

export async function listTrainingRequirements(
  params: ListTrainingRequirementsParams = {},
): Promise<TrainingRequirementRead[]> {
  const sp = new URLSearchParams();
  if (params.include_inactive) sp.set("include_inactive", "true");
  if (typeof params.limit === "number") sp.set("limit", String(params.limit));
  if (typeof params.offset === "number") sp.set("offset", String(params.offset));
  const qs = sp.toString();
  const path = qs ? `/training/requirements?${qs}` : "/training/requirements";
  return cachedTrainingGet(`requirements:${qs || "all"}`, 3 * 60_000, () =>
    apiGet<TrainingRequirementRead[]>(path, { headers: authHeaders() }),
  );
}

export async function createTrainingRequirement(payload: TrainingRequirementCreate): Promise<TrainingRequirementRead> {
  const created = await apiPost<TrainingRequirementRead>("/training/requirements", payload, {
    headers: authHeaders(),
  });
  invalidateTrainingServiceCache();
  return created;
}

export async function updateTrainingRequirement(requirementId: string, payload: TrainingRequirementUpdate): Promise<TrainingRequirementRead> {
  const updated = await apiPost<TrainingRequirementRead>(
    `/training/requirements/${encodeURIComponent(requirementId)}`,
    payload,
    { method: "PUT", headers: authHeaders() } as RequestInit,
  );
  invalidateTrainingServiceCache();
  return updated;
}

export async function deleteTrainingRequirement(requirementId: string): Promise<{ id: string; action: string; message: string; soft_deleted: boolean }> {
  const result = await apiPost<{ id: string; action: string; message: string; soft_deleted: boolean }>(
    `/training/requirements/${encodeURIComponent(requirementId)}`,
    {},
    { method: "DELETE", headers: authHeaders() } as RequestInit,
  );
  invalidateTrainingServiceCache();
  return result;
}

export async function listTrainingEventParticipants(eventId: string): Promise<TrainingEventParticipantRead[]> {
  const key = `event-participants:${eventId}`;
  return cachedTrainingGet(key, 30_000, () =>
    apiGet<TrainingEventParticipantRead[]>(`/training/events/${encodeURIComponent(eventId)}/participants`, {
      headers: authHeaders(),
    }),
  );
}

// ---------------------------------------------------------------------------
// EVENTS
// ---------------------------------------------------------------------------

export interface ListEventsParams {
  course_pk?: string;
  from_date?: string; // ISO date
  to_date?: string;   // ISO date
  limit?: number;
  offset?: number;
}

/**
 * List training events for the current AMO with optional filters.
 */
export async function listTrainingEvents(
  params: ListEventsParams = {},
): Promise<TrainingEventRead[]> {
  const sp = new URLSearchParams();

  if (params.course_pk) sp.set("course_pk", params.course_pk);
  if (params.from_date) sp.set("from_date", params.from_date);
  if (params.to_date) sp.set("to_date", params.to_date);
  if (typeof params.limit === "number") sp.set("limit", String(params.limit));
  if (typeof params.offset === "number") sp.set("offset", String(params.offset));

  const qs = sp.toString();
  const path = qs ? `/training/events?${qs}` : "/training/events";

  return cachedTrainingGet(`events:${qs || "all"}`, 60_000, () =>
    apiGet<TrainingEventRead[]>(path, {
      headers: authHeaders(),
    }),
  );
}

/**
 * Create a training event (Quality / AMO admin only).
 */
export async function createTrainingEvent(
  payload: TrainingEventCreate,
): Promise<TrainingEventRead> {
  const created = await apiPost<TrainingEventRead>("/training/events", payload, {
    headers: authHeaders(),
  });
  invalidateTrainingServiceCache();
  return created;
}

export async function createTrainingEventBatch(
  payload: TrainingEventBatchScheduleCreate,
): Promise<TrainingEventBatchScheduleRead> {
  const created = await apiPost<TrainingEventBatchScheduleRead>("/training/events/batch-schedule", payload, {
    headers: authHeaders(),
  });
  invalidateTrainingServiceCache();
  return created;
}

export async function autoGroupTrainingEvents(
  payload: TrainingAutoGroupScheduleCreate,
): Promise<TrainingAutoGroupScheduleRead> {
  const created = await apiPost<TrainingAutoGroupScheduleRead>("/training/events/auto-group-schedule", payload, {
    headers: authHeaders(),
  });
  invalidateTrainingServiceCache();
  return created;
}

/**
 * Update a training event (Quality / AMO admin only).
 */
export async function updateTrainingEvent(
  eventId: string,
  payload: TrainingEventUpdate,
): Promise<TrainingEventRead> {
  const updated = await apiPost<TrainingEventRead>(
    `/training/events/${encodeURIComponent(eventId)}`,
    payload,
    {
      method: "PUT",
      headers: authHeaders(),
    } as RequestInit,
  );
  invalidateTrainingServiceCache();
  return updated;
}

// ---------------------------------------------------------------------------
// EVENT PARTICIPANTS
// ---------------------------------------------------------------------------

/**
 * Add a participant to a training event (Quality / AMO admin only).
 */
export async function addTrainingEventParticipant(
  payload: TrainingEventParticipantCreate,
): Promise<TrainingEventParticipantRead> {
  const created = await apiPost<TrainingEventParticipantRead>(
    "/training/event-participants",
    payload,
    {
      headers: authHeaders(),
    },
  );
  invalidateTrainingServiceCache();
  return created;
}

/**
 * Update a participant's status in an event (Quality / AMO admin only).
 */
export async function updateTrainingEventParticipant(
  participantId: string,
  payload: TrainingEventParticipantUpdate,
): Promise<TrainingEventParticipantRead> {
  const updated = await apiPost<TrainingEventParticipantRead>(
    `/training/event-participants/${encodeURIComponent(participantId)}`,
    payload,
    {
      method: "PUT",
      headers: authHeaders(),
    } as RequestInit,
  );
  invalidateTrainingServiceCache();
  return updated;
}

// ---------------------------------------------------------------------------
// TRAINING FILES (EVIDENCE DOWNLOADS)
// ---------------------------------------------------------------------------

function buildSpeed(
  loadedBytes: number,
  totalBytes: number | undefined,
  startedAt: number
): TransferProgress {
  const elapsedSeconds = Math.max((performance.now() - startedAt) / 1000, 0.001);
  const megaBytesPerSecond = loadedBytes / (1024 * 1024) / elapsedSeconds;
  const megaBitsPerSecond = megaBytesPerSecond * 8;
  const percent = totalBytes ? Math.min((loadedBytes / totalBytes) * 100, 100) : undefined;
  return {
    loadedBytes,
    totalBytes,
    percent,
    megaBytesPerSecond,
    megaBitsPerSecond,
  };
}

export interface ListTrainingFilesParams {
  owner_user_id?: string;
  kind?: string;
  review_status?: TrainingFileReviewStatus;
  limit?: number;
  offset?: number;
}

export async function listTrainingFiles(params: ListTrainingFilesParams = {}): Promise<TrainingFileRead[]> {
  const sp = new URLSearchParams();
  if (params.owner_user_id) sp.set("owner_user_id", params.owner_user_id);
  if (params.kind) sp.set("kind", params.kind);
  if (params.review_status) sp.set("review_status", params.review_status);
  if (typeof params.limit === "number") sp.set("limit", String(params.limit));
  if (typeof params.offset === "number") sp.set("offset", String(params.offset));
  const qs = sp.toString();
  const path = qs ? `/training/files?${qs}` : "/training/files";
  return cachedTrainingGet(`files:${qs || "all"}`, 45_000, () =>
    apiGet<TrainingFileRead[]>(path, {
      headers: authHeaders(),
    }),
  );
}

export async function uploadTrainingFile(payload: FormData): Promise<TrainingFileRead> {
  const uploaded = await apiPost<TrainingFileRead>("/training/files/upload", payload, {
    method: "POST",
    headers: authHeaders(),
  } as RequestInit);
  invalidateTrainingServiceCache();
  return uploaded;
}

export async function downloadTrainingFile(
  fileId: string,
  onProgress?: (progress: TransferProgress) => void
): Promise<DownloadedFile> {
  const startedAt = performance.now();
  return downloadWithXhr({
    url: `${getApiBaseUrl()}/training/files/${encodeURIComponent(fileId)}/download`,
    headers: authHeaders() as Record<string, string>,
    fallbackFilename: `training_file_${fileId}`,
    onProgress: onProgress
      ? (loaded, total) => onProgress(buildSpeed(loaded, total, startedAt))
      : undefined,
  });
}

export async function warmTrainingUserRecordPdf(userId: string): Promise<{ queued: boolean; ready: boolean }> {
  return apiPost<{ queued: boolean; ready: boolean }>(
    `/training/users/${encodeURIComponent(userId)}/record-pdf/warm`,
    {},
    { headers: authHeaders() }
  );
}

export async function waitForTrainingUserRecordPdfReady(
  userId: string,
  opts: { attempts?: number; intervalMs?: number } = {},
): Promise<boolean> {
  const attempts = Math.max(1, opts.attempts ?? 12);
  const intervalMs = Math.max(150, opts.intervalMs ?? 500);
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const response = await warmTrainingUserRecordPdf(userId);
    if (response.ready) return true;
    await delay(intervalMs);
  }
  return false;
}

export async function downloadTrainingUserRecordPdf(userId: string, onProgress?: (progress: TransferProgress) => void): Promise<DownloadedFile> {
  const startedAt = performance.now();
  return downloadWithXhr({
    url: `${getApiBaseUrl()}/training/users/${encodeURIComponent(userId)}/record-pdf`,
    headers: authHeaders() as Record<string, string>,
    fallbackFilename: `training-record-${userId}.pdf`,
    onProgress: onProgress
      ? (loaded, total) => onProgress(buildSpeed(loaded, total, startedAt))
      : undefined,
    retries: 3,
    retryStatuses: [404, 408, 409, 423, 425, 429, 500, 502, 503, 504],
  });
}

export async function downloadTrainingUserEvidencePack(userId: string, onProgress?: (progress: TransferProgress) => void): Promise<DownloadedFile> {
  const startedAt = performance.now();
  return downloadWithXhr({
    url: `${getApiBaseUrl()}/training/users/${encodeURIComponent(userId)}/evidence-pack`,
    headers: authHeaders() as Record<string, string>,
    fallbackFilename: `training-evidence-${userId}.zip`,
    onProgress: onProgress
      ? (loaded, total) => onProgress(buildSpeed(loaded, total, startedAt))
      : undefined,
    retries: 3,
  });
}

// ---------------------------------------------------------------------------
 // TRAINING RECORDS
// ---------------------------------------------------------------------------

export interface ListTrainingRecordsParams {
  user_id?: string;
  course_pk?: string;
  limit?: number;
  offset?: number;
}

/**
 * List training completion records for the current AMO.
 *
 * Supports server filtering; avoid loading records for all users when viewing a single profile.
 */
export async function listTrainingRecords(
  params: ListTrainingRecordsParams = {},
): Promise<TrainingRecordRead[]> {
  const sp = new URLSearchParams();
  if (params.user_id) sp.set("user_id", params.user_id);
  if (params.course_pk) sp.set("course_pk", params.course_pk);
  if (typeof params.limit === "number") sp.set("limit", String(params.limit));
  if (typeof params.offset === "number") sp.set("offset", String(params.offset));
  if (!sp.has("limit")) sp.set("limit", "50");

  const qs = sp.toString();
  const path = qs ? `/training/records?${qs}` : "/training/records?limit=50";

  try {
    return await cachedTrainingGet(`records:${qs || "all"}`, 45_000, () =>
      apiGet<TrainingRecordRead[]>(path, {
        headers: authHeaders(),
      }),
    );
  } catch (error: any) {
    const message = String(error?.message || "").toLowerCase();
    if (message.includes("deadlock")) {
      await delay(120);
      return cachedTrainingGet(`records:${qs || "all"}`, 45_000, () =>
        apiGet<TrainingRecordRead[]>(path, {
          headers: authHeaders(),
        }),
        true,
      );
    }
    throw error;
  }
}

/**
 * Create a training completion record (Quality / AMO admin only).
 */
export async function createTrainingRecord(
  payload: TrainingRecordCreate,
): Promise<TrainingRecordRead> {
  const created = await apiPost<TrainingRecordRead>("/training/records", payload, {
    headers: authHeaders(),
  });
  invalidateTrainingServiceCache();
  return created;
}

export async function updateTrainingRecord(
  recordId: string,
  payload: TrainingRecordUpdate,
): Promise<TrainingRecordRead> {
  const updated = await apiPut<TrainingRecordRead>(`/training/records/${encodeURIComponent(recordId)}`, payload, {
    headers: authHeaders(),
  });
  invalidateTrainingServiceCache();
  return updated;
}

export async function deleteTrainingRecord(recordId: string): Promise<void> {
  await apiDelete<void>(`/training/records/${encodeURIComponent(recordId)}`, undefined, {
    headers: authHeaders(),
  });
  invalidateTrainingServiceCache();
}

// ---------------------------------------------------------------------------
// DEFERRALS (QWI-026)
// ---------------------------------------------------------------------------

/**
 * Request a training deferral.
 * Any active user can request their own; Quality/Admin can request for others.
 */
export async function createTrainingDeferralRequest(
  payload: TrainingDeferralRequestCreate,
): Promise<TrainingDeferralRequestRead> {
  const created = await apiPost<TrainingDeferralRequestRead>("/training/deferrals", payload, {
    headers: authHeaders(),
  });
  invalidateTrainingServiceCache();
  return created;
}

/**
 * Approve / reject / amend a deferral request (Quality / AMO admin only).
 */
export async function updateTrainingDeferralRequest(
  deferralId: string,
  payload: TrainingDeferralRequestUpdate,
): Promise<TrainingDeferralRequestRead> {
  const updated = await apiPost<TrainingDeferralRequestRead>(
    `/training/deferrals/${encodeURIComponent(deferralId)}`,
    payload,
    {
      method: "PUT",
      headers: authHeaders(),
    } as RequestInit,
  );
  invalidateTrainingServiceCache();
  return updated;
}

/**
 * List deferral requests for the current user.
 */
export async function listMyTrainingDeferrals(): Promise<TrainingDeferralRequestRead[]> {
  return apiGet<TrainingDeferralRequestRead[]>("/training/deferrals/me", {
    headers: authHeaders(),
  });
}

export interface ListTrainingDeferralsParams {
  status?: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
  user_id?: string;
  limit?: number;
  offset?: number;
}

export async function listTrainingDeferrals(
  params: ListTrainingDeferralsParams = {},
): Promise<TrainingDeferralRequestRead[]> {
  const sp = new URLSearchParams();
  if (params.status) sp.set("status", params.status);
  if (params.user_id) sp.set("user_id", params.user_id);
  if (params.limit) sp.set("limit", String(params.limit));
  if (params.offset) sp.set("offset", String(params.offset));
  const qs = sp.toString();
  const path = qs ? `/training/deferrals?${qs}` : "/training/deferrals";
  return cachedTrainingGet(`deferrals:${qs || "all"}`, 45_000, () =>
    apiGet<TrainingDeferralRequestRead[]>(path, {
      headers: authHeaders(),
    }),
  );
}

// ---------------------------------------------------------------------------
// STATUS VIEWS
// ---------------------------------------------------------------------------

/**
 * Training status for the current logged-in user.
 */
export async function getMyTrainingStatus(): Promise<TrainingStatusItem[]> {
  return cachedTrainingGet("status:me", 30_000, () =>
    apiGet<TrainingStatusItem[]>("/training/status/me", {
      headers: authHeaders(),
    }),
  );
}

export interface TrainingStatusBulkResponse {
  users: Record<string, TrainingStatusItem[]>;
}

export async function getBulkTrainingStatusForUsers(
  userIds: string[],
): Promise<TrainingStatusBulkResponse> {
  const sortedIds = [...userIds].sort();
  const cacheKey = `status:bulk:${sortedIds.join(",")}`;
  try {
    return await cachedTrainingGet(cacheKey, 30_000, () =>
      apiPost<TrainingStatusBulkResponse>(
        "/training/status/users/bulk",
        { user_ids: sortedIds },
        {
          headers: authHeaders(),
        },
      ),
    );
  } catch {
    const users: Record<string, TrainingStatusItem[]> = {};
    await Promise.all(
      userIds.map(async (userId) => {
        try {
          users[userId] = await getUserTrainingStatus(userId);
        } catch {
          users[userId] = [];
        }
      }),
    );
    return { users };
  }
}

/**
 * Training status for a specific user (Quality / AMO admin only).
 */
export async function getUserTrainingStatus(
  userId: string,
): Promise<TrainingStatusItem[]> {
  return cachedTrainingGet(`status:user:${userId}`, 30_000, () =>
    apiGet<TrainingStatusItem[]>(
      `/training/status/users/${encodeURIComponent(userId)}`,
      {
        headers: authHeaders(),
      },
    ),
  );
}

export async function getMyTrainingAccessState(): Promise<TrainingAccessState> {
  return apiGet<TrainingAccessState>("/training/status/access/me", {
    headers: authHeaders(),
  });
}

export async function getUserTrainingAccessState(userId: string): Promise<TrainingAccessState> {
  return apiGet<TrainingAccessState>(`/training/status/access/users/${encodeURIComponent(userId)}`, {
    headers: authHeaders(),
  });
}

export async function runTrainingNotificationSweep(): Promise<{ notifications_created: number }> {
  return apiPost<{ notifications_created: number }>("/training/compliance/notifications/sweep", {}, {
    headers: authHeaders(),
  });
}

// ---------------------------------------------------------------------------
// NOTIFICATIONS
// ---------------------------------------------------------------------------

export interface ListTrainingNotificationsParams {
  unread_only?: boolean;
  limit?: number;
  offset?: number;
}

export async function listTrainingNotifications(
  params: ListTrainingNotificationsParams = {},
): Promise<TrainingNotificationRead[]> {
  const sp = new URLSearchParams();
  if (params.unread_only) sp.set("unread_only", "true");
  if (params.limit) sp.set("limit", String(params.limit));
  if (params.offset) sp.set("offset", String(params.offset));
  const qs = sp.toString();
  const path = qs ? `/training/notifications/me?${qs}` : "/training/notifications/me";
  return apiGet<TrainingNotificationRead[]>(path, {
    headers: authHeaders(),
  });
}

export async function markTrainingNotificationRead(
  notificationId: string,
  payload: TrainingNotificationMarkRead,
): Promise<TrainingNotificationRead> {
  return apiPost<TrainingNotificationRead>(
    `/training/notifications/${encodeURIComponent(notificationId)}/read`,
    payload,
    {
      method: "PUT",
      headers: authHeaders(),
    } as RequestInit,
  );
}

export async function markAllTrainingNotificationsRead(): Promise<{ ok: boolean }> {
  return apiPost<{ ok: boolean }>(
    "/training/notifications/me/read-all",
    {},
    {
      headers: authHeaders(),
    },
  );
}

export async function listTrainingCertificates(userId?: string, opts: { limit?: number; offset?: number } = {}): Promise<TrainingRecordRead[]> {
  const sp = new URLSearchParams();
  if (userId) sp.set("user_id", userId);
  if (typeof opts.limit === "number") sp.set("limit", String(opts.limit));
  if (typeof opts.offset === "number") sp.set("offset", String(opts.offset));
  const qs = sp.toString();
  const path = qs ? `/training/certificates?${qs}` : "/training/certificates";
  return cachedTrainingGet(`certificates:${qs || "all"}`, 45_000, () => apiGet<TrainingRecordRead[]>(path, { headers: authHeaders() }));
}

export async function issueTrainingCertificate(recordId: string): Promise<TrainingRecordRead> {
  const issued = await apiPost<TrainingRecordRead>(
    `/training/certificates/issue/${encodeURIComponent(recordId)}`,
    {},
    { headers: authHeaders() },
  );
  invalidateTrainingServiceCache();
  return issued;
}

export type PublicCertificateVerification = {
  status: "VALID" | "EXPIRED" | "NOT_FOUND" | "MALFORMED";
  certificate_number: string;
  trainee_name?: string;
  course_title?: string;
  issue_date?: string;
  valid_until?: string | null;
  issuer?: string;
};

export async function verifyCertificatePublic(certificateNumber: string): Promise<PublicCertificateVerification> {
  const base = getApiBaseUrl() || (import.meta.env.DEV ? (import.meta.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8080") : "");
  const url = `${base}/public/certificates/verify/${encodeURIComponent(certificateNumber)}`;
  const res = await fetch(url, { method: "GET" });
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Verification service unavailable");
  }
  const data = (await res.json()) as PublicCertificateVerification;
  if (!res.ok) {
    throw new Error((data as any)?.message || "Verification service unavailable");
  }
  return data;
}

export async function downloadTrainingCertificateArtifact(
  recordId: string,
  options: TrainingCertificateArtifactOptions = {},
): Promise<DownloadedFile> {
  const sp = new URLSearchParams();
  Object.entries(options).forEach(([key, value]) => {
    if (value) sp.set(key, String(value));
  });
  const qs = sp.toString();
  const url = `${getApiBaseUrl()}${qs ? `/training/certificates/artifact/${encodeURIComponent(recordId)}?${qs}` : `/training/certificates/artifact/${encodeURIComponent(recordId)}`}`;
  return downloadWithFetch(url, { headers: authHeaders() }, `training-certificate-${recordId}.pdf`, 180_000);
}


export async function listTrainingRecordsByUsers(
  userIds: string[],
  opts: { limit?: number; offset?: number } = {},
): Promise<TrainingRecordRead[]> {
  const sortedIds = [...new Set(userIds.map((id) => String(id).trim()).filter(Boolean))].sort();
  if (sortedIds.length === 0) return [];
  const key = `records:users:${sortedIds.join(",")}:${opts.limit ?? 500}:${opts.offset ?? 0}`;
  return cachedTrainingGet(key, 45_000, () =>
    apiPost<TrainingRecordRead[]>(
      "/training/records/by-users",
      { user_ids: sortedIds, limit: opts.limit ?? 500, offset: opts.offset ?? 0 },
      { headers: authHeaders() },
    ),
  );
}

export async function getTrainingUserDetailBundle(
  userId: string,
  opts: { recordsLimit?: number; deferralsLimit?: number; filesLimit?: number; eventsLimit?: number } = {},
): Promise<TrainingUserDetailBundle> {
  const sp = new URLSearchParams();
  sp.set("records_limit", String(opts.recordsLimit ?? 50));
  sp.set("deferrals_limit", String(opts.deferralsLimit ?? 50));
  sp.set("files_limit", String(opts.filesLimit ?? 50));
  sp.set("events_limit", String(opts.eventsLimit ?? 20));
  const qs = sp.toString();
  return cachedTrainingGet(`detail-bundle:${userId}:${qs}`, 30_000, () =>
    apiGet<TrainingUserDetailBundle>(`/training/users/${encodeURIComponent(userId)}/detail-bundle?${qs}`, {
      headers: authHeaders(),
    }),
  );
}

export async function prefetchTrainingUserDetailBundle(
  userId: string,
  opts: { warmPdf?: boolean } = {},
): Promise<void> {
  const tasks: Array<Promise<unknown>> = [
    getTrainingUserDetailBundle(userId, { recordsLimit: 25, deferralsLimit: 25, filesLimit: 25, eventsLimit: 10 }),
  ];
  if (opts.warmPdf) tasks.push(warmTrainingUserRecordPdf(userId));
  await Promise.allSettled(tasks);
}
